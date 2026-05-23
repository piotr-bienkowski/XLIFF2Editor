#!/usr/bin/env python3
"""
XLIFF 2.2 to memoQ MQXLIFF Merger
Merges translations from a XLIFF 2.2 file back into the original MQXLIFF file(s).
"""

import sys
from pathlib import Path
from lxml import etree

NS_XLIFF12 = 'urn:oasis:names:tc:xliff:document:1.2'
NS = {'xliff12': NS_XLIFF12}
NS_XLIFF22 = {'xliff22': 'urn:oasis:names:tc:xliff:document:2.0'}

XLIFF22_STATE_TO_MQ = {
    'initial':                    'NotStarted',
    'translated':                 'PartiallyEdited',
    'reviewed':                   'Ackknowledged',    # schema typo preserved
    'final':                      'ManuallyConfirmed',
    'needs-review-translation':   'PartiallyEdited',
    'needs-review-adaptation':    'PartiallyEdited',
    'needs-review-l10n':          'PartiallyEdited',
}


def map_xliff22_state_to_mq(state):
    if not state:
        return 'Edited'
    return XLIFF22_STATE_TO_MQ.get(state, 'Edited')


def _fill_element(elem, parts):
    for part in parts:
        if isinstance(part, str):
            if len(elem):
                elem[-1].tail = (elem[-1].tail or '') + part
            else:
                elem.text = (elem.text or '') + part
        else:
            elem.append(part)


def extract_content_from_xliff22(element):
    """
    Convert XLIFF 2.2 target content back to XLIFF 1.2 format.
    pc → g,  ph → x
    """
    result = []

    if element.text:
        result.append(element.text)

    for child in element:
        tag = etree.QName(child).localname

        if tag == 'pc':
            g = etree.Element('{%s}g' % NS_XLIFF12)
            if 'id' in child.attrib:
                g.set('id', child.get('id'))
            _fill_element(g, extract_content_from_xliff22(child))
            result.append(g)
        elif tag == 'ph':
            x = etree.Element('{%s}x' % NS_XLIFF12)
            if 'id' in child.attrib:
                x.set('id', child.get('id'))
            if child.text:
                x.text = child.text
            result.append(x)
        else:
            new = etree.Element(child.tag)
            new.attrib.update(child.attrib)
            _fill_element(new, extract_content_from_xliff22(child))
            result.append(new)

        if child.tail:
            result.append(child.tail)

    return result


def build_segment_map(file_elem):
    """
    Build {unit_id: {segment_position: {target_content, state}}} from a XLIFF 2.2 file element.
    """
    segment_map = {}
    ns = 'urn:oasis:names:tc:xliff:document:2.0'

    for unit in file_elem.findall(f'{{{ns}}}unit'):
        unit_id = unit.get('id')
        segment_map[unit_id] = {}
        pos = 0
        for segment in unit.findall(f'{{{ns}}}segment'):
            pos += 1
            state = segment.get('state')
            target_elem = segment.find(f'{{{ns}}}target')
            if target_elem is not None:
                segment_map[unit_id][pos] = {
                    'target_content': extract_content_from_xliff22(target_elem),
                    'state': state,
                }

    return segment_map


def update_mqxliff_targets(mqxliff_path, segment_map, output_path):
    """
    Update target elements in an MQXLIFF file from the segment map and write to output_path.
    Returns (updated_count, skipped_count).
    """
    tree = etree.parse(mqxliff_path)
    root = tree.getroot()
    MQ_NS = 'MQXliff'

    updated = 0
    skipped = 0

    for trans_unit in root.findall('.//xliff12:trans-unit', NS):
        unit_id = trans_unit.get('id')
        if unit_id not in segment_map or 1 not in segment_map[unit_id]:
            skipped += 1
            continue

        data = segment_map[unit_id][1]
        if not data.get('target_content'):
            skipped += 1
            continue

        target = trans_unit.find('xliff12:target', NS)
        if target is None:
            source = trans_unit.find('xliff12:source', NS)
            if source is not None:
                idx = list(trans_unit).index(source) + 1
            else:
                idx = 0
            target = etree.Element('{%s}target' % NS_XLIFF12)
            from lxml.etree import QName
            target.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
            trans_unit.insert(idx, target)

        target.clear()
        target.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
        _fill_element(target, data['target_content'])

        # Update mq:status
        new_mq_status = map_xliff22_state_to_mq(data['state'])
        trans_unit.set(f'{{{MQ_NS}}}status', new_mq_status)

        updated += 1

    tree.write(str(output_path), encoding='utf-8', xml_declaration=True, pretty_print=False)
    return updated, skipped


def find_mqxliff_for_file_id(file_id, mqxliff_dir):
    """
    Find the MQXLIFF file corresponding to the given file_id in mqxliff_dir.
    Strategies: exact match → add extension → case-insensitive.
    """
    mqxliff_dir = Path(mqxliff_dir)
    extensions = ('.mqxliff', '.xliff', '.xlf')

    # Strategy 1: exact match
    exact = mqxliff_dir / file_id
    if exact.exists():
        return exact

    # Strategy 2: add .mqxliff if not already an xliff extension
    if not any(file_id.lower().endswith(e) for e in extensions):
        with_ext = mqxliff_dir / f"{file_id}.mqxliff"
        if with_ext.exists():
            return with_ext

    # Strategy 3: case-insensitive search for all xliff-like files
    file_id_lower = file_id.lower()
    for candidate in mqxliff_dir.iterdir():
        if candidate.suffix.lower() in extensions:
            if candidate.name.lower() == file_id_lower:
                return candidate

    return None


def batch_merge_xliff22_to_mqxliff(xliff22_path, mqxliff_dir, output_dir, dry_run=False):
    """
    Process all file elements in the XLIFF 2.2 and merge back into corresponding MQXLIFF files.
    """
    tree = etree.parse(xliff22_path)
    root = tree.getroot()
    ns = 'urn:oasis:names:tc:xliff:document:2.0'

    file_elements = root.findall(f'.//{{{ns}}}file')
    print(f"Found {len(file_elements)} file element(s) in XLIFF 2.2")
    print("=" * 70)

    output_dir = Path(output_dir)
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    for idx, file_elem in enumerate(file_elements, 1):
        file_id = file_elem.get('id')
        print(f"\n[{idx}/{len(file_elements)}] Processing file ID: {file_id}")
        print("-" * 70)

        mqxliff_path = find_mqxliff_for_file_id(file_id, mqxliff_dir)
        if mqxliff_path is None:
            print(f"  ✗ No matching MQXLIFF file found for: {file_id}")
            results.append({'file_id': file_id, 'status': 'no_match'})
            continue

        print(f"  ✓ Matched to: {mqxliff_path.name}")
        segment_map = build_segment_map(file_elem)
        total = sum(len(v) for v in segment_map.values())
        print(f"  Segments to merge: {total}")

        if dry_run:
            print(f"  [DRY RUN] Would write to: {output_dir / mqxliff_path.name}")
            results.append({'file_id': file_id, 'status': 'dry_run', 'segments': total})
            continue

        output_path = output_dir / mqxliff_path.name
        try:
            updated, skipped = update_mqxliff_targets(mqxliff_path, segment_map, output_path)
            print(f"  ✓ Updated {updated} segments")
            if skipped:
                print(f"  ⚠ Skipped {skipped} segments (no translation)")
            print(f"  ✓ Written to: {output_path}")
            results.append({
                'file_id': file_id, 'status': 'success',
                'mqxliff': str(mqxliff_path), 'output': str(output_path),
                'updated': updated, 'skipped': skipped,
            })
        except Exception as e:
            print(f"  ✗ Error: {e}")
            results.append({'file_id': file_id, 'status': 'error', 'error': str(e)})

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Merge XLIFF 2.2 translations back into memoQ MQXLIFF files',
    )
    parser.add_argument('xliff22', help='XLIFF 2.2 file')
    parser.add_argument('--mqxliff-dir', required=True, help='Directory with original MQXLIFF files')
    parser.add_argument('--output-dir', required=True, help='Output directory for updated MQXLIFF files')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    xliff22_path = Path(args.xliff22)
    if not xliff22_path.exists():
        print(f"Error: {xliff22_path} not found", file=sys.stderr)
        sys.exit(1)

    mqxliff_dir = Path(args.mqxliff_dir)
    if not mqxliff_dir.exists():
        print(f"Error: {mqxliff_dir} not found", file=sys.stderr)
        sys.exit(1)

    results = batch_merge_xliff22_to_mqxliff(xliff22_path, mqxliff_dir, args.output_dir, args.dry_run)

    success = sum(1 for r in results if r['status'] == 'success')
    no_match = sum(1 for r in results if r['status'] == 'no_match')
    errors = sum(1 for r in results if r['status'] == 'error')
    print(f"\n✓ Merged: {success}  ⚠ No match: {no_match}  ✗ Errors: {errors}")
    sys.exit(0 if not errors and not no_match else 1)


if __name__ == '__main__':
    main()
