#!/usr/bin/env python3
"""
XLIFF 2.2 to Wordfast Pro TXLF Merger

Merges translations from a XLIFF 2.2 file back into the original TXLF file(s).
Original TXLF inline tag structure (bx/ex, bpt/ept content, ph/x attrs) is
preserved by matching XLIFF 2.2 <pc>/<ph> ids against the TXLF source's tag ids
and cloning the corresponding source-side elements into the new target.
"""

import copy
import sys
from pathlib import Path
from lxml import etree

NS_XLIFF12 = 'urn:oasis:names:tc:xliff:document:1.2'
NS_XLIFF22 = 'urn:oasis:names:tc:xliff:document:2.0'
NS_GS4TR   = 'http://www.gs4tr.org/schema/xliff-ext'
NS_XML     = 'http://www.w3.org/XML/1998/namespace'
NS12 = {'x12': NS_XLIFF12}

XLIFF22_STATE_TO_TXLF = {
    'initial':                    'needs-translation',
    'translated':                 'translated',
    'reviewed':                   'signed-off',
    'final':                      'signed-off',
    'needs-review-translation':   'needs-review-translation',
    'needs-review-adaptation':    'needs-review-translation',
    'needs-review-l10n':          'needs-review-translation',
}


def map_xliff22_state_to_txlf(state):
    if not state:
        return 'translated'
    return XLIFF22_STATE_TO_TXLF.get(state, 'translated')


def _fill_element(elem, parts):
    for part in parts:
        if isinstance(part, str):
            if len(elem):
                elem[-1].tail = (elem[-1].tail or '') + part
            else:
                elem.text = (elem.text or '') + part
        else:
            elem.append(part)


def _clone_element(elem):
    """Deep-copy an element with its attrs, text, tail, and children."""
    new = etree.Element(elem.tag)
    new.attrib.update(elem.attrib)
    new.text = elem.text
    for c in elem:
        new.append(copy.deepcopy(c))
    return new


def _build_source_tag_lookup(source_elem):
    """Build lookup tables from the TXLF <source> to be used when reconstructing
    the TXLF <target>.

    Returns dict with keys:
      'bx': {rid_or_id: <bx element>}
      'ex': {rid_or_id: <ex element>}
      'bpt': {rid_or_id: <bpt element>}
      'ept': {rid_or_id: <ept element>}
      'ph':  {id: <ph element>}
      'x':   {id: <x element>}
      'g':   {id: <g element>}
    """
    lookup = {k: {} for k in ('bx', 'ex', 'bpt', 'ept', 'ph', 'x', 'g')}
    if source_elem is None:
        return lookup
    for el in source_elem.iter():
        local = etree.QName(el).localname
        if local in ('bx', 'ex', 'bpt', 'ept'):
            key = el.get('rid') or el.get('id')
            if key is not None:
                lookup[local][key] = el
        elif local in ('ph', 'x', 'g'):
            key = el.get('id')
            if key is not None:
                lookup[local][key] = el
    return lookup


def _rebuild_txlf_target_content(xliff22_target, source_lookup):
    """Walk XLIFF 2.2 target, emitting a list of strings and TXLF elements.

    For each <pc id="X">…</pc>:
      - if source has bx/ex pair with rid=X → emit <bx>…content…<ex>
      - elif source has bpt/ept pair with rid=X → emit <bpt>…content…<ept>
      - elif source has g id=X → emit <g id="X">…content…</g>
      - else → emit generic <g id="X" ctype="type"> as fallback

    For each <ph id="X"/>:
      - if source has ph id=X → clone (preserves content)
      - elif source has x id=X → clone
      - else → emit generic <x id="X" ctype="type"/>
    """
    parts = []
    if xliff22_target.text:
        parts.append(xliff22_target.text)

    for child in xliff22_target:
        local = etree.QName(child).localname

        if local == 'pc':
            pc_id = child.get('id')
            pc_type = child.get('type', '')
            emitted = False

            if pc_id in source_lookup['bx']:
                bx_orig = source_lookup['bx'][pc_id]
                parts.append(_clone_element(bx_orig))
                # remove tail from clone (we manage tails ourselves)
                if parts[-1].tail is not None:
                    parts[-1].tail = None
                parts.extend(_rebuild_txlf_target_content(child, source_lookup))
                ex_orig = source_lookup['ex'].get(pc_id)
                if ex_orig is not None:
                    ex_new = _clone_element(ex_orig)
                    ex_new.tail = None
                    parts.append(ex_new)
                emitted = True

            elif pc_id in source_lookup['bpt']:
                bpt_orig = source_lookup['bpt'][pc_id]
                bpt_new = _clone_element(bpt_orig)
                bpt_new.tail = None
                parts.append(bpt_new)
                parts.extend(_rebuild_txlf_target_content(child, source_lookup))
                ept_orig = source_lookup['ept'].get(pc_id)
                if ept_orig is not None:
                    ept_new = _clone_element(ept_orig)
                    ept_new.tail = None
                    parts.append(ept_new)
                emitted = True

            elif pc_id in source_lookup['g']:
                g_orig = source_lookup['g'][pc_id]
                g_new = etree.Element(g_orig.tag)
                g_new.attrib.update(g_orig.attrib)
                _fill_element(g_new, _rebuild_txlf_target_content(child, source_lookup))
                parts.append(g_new)
                emitted = True

            if not emitted:
                g_new = etree.Element('{%s}g' % NS_XLIFF12)
                if pc_id is not None:
                    g_new.set('id', pc_id)
                if pc_type:
                    g_new.set('ctype', pc_type)
                _fill_element(g_new, _rebuild_txlf_target_content(child, source_lookup))
                parts.append(g_new)

        elif local == 'ph':
            ph_id = child.get('id')
            ph_type = child.get('type', '')
            if ph_id in source_lookup['ph']:
                orig = source_lookup['ph'][ph_id]
                new = _clone_element(orig)
                new.tail = None
                parts.append(new)
            elif ph_id in source_lookup['x']:
                orig = source_lookup['x'][ph_id]
                new = _clone_element(orig)
                new.tail = None
                parts.append(new)
            else:
                x_new = etree.Element('{%s}x' % NS_XLIFF12)
                if ph_id is not None:
                    x_new.set('id', ph_id)
                if ph_type:
                    x_new.set('ctype', ph_type)
                parts.append(x_new)

        else:
            # Preserve unknown elements
            new = etree.Element(child.tag)
            new.attrib.update(child.attrib)
            _fill_element(new, _rebuild_txlf_target_content(child, source_lookup))
            parts.append(new)

        if child.tail:
            parts.append(child.tail)

    return parts


def build_segment_map_from_file_element(file_elem):
    """Return {unit_id: {segment_position: {'target_elem': <pyobj>, 'state': str}}}."""
    segment_map = {}
    for unit in file_elem.findall(f'{{{NS_XLIFF22}}}unit'):
        unit_id = unit.get('id')
        if unit_id is None:
            continue
        segment_map[unit_id] = {}
        pos = 0
        for segment in unit.findall(f'{{{NS_XLIFF22}}}segment'):
            pos += 1
            state = segment.get('state')
            target_elem = segment.find(f'{{{NS_XLIFF22}}}target')
            if target_elem is not None:
                segment_map[unit_id][pos] = {
                    'target_elem': target_elem,
                    'state': state,
                }
    return segment_map


def update_txlf_targets(txlf_path, segment_map, output_path):
    """Update <target> elements in a TXLF file per segment_map, write to output_path.

    Returns (updated, skipped, total_tus).
    """
    tree = etree.parse(str(txlf_path))
    root = tree.getroot()

    updated = 0
    skipped = 0
    total = 0

    for trans_unit in root.findall(f'.//{{{NS_XLIFF12}}}trans-unit'):
        total += 1
        unit_id = trans_unit.get('id')
        if unit_id not in segment_map or 1 not in segment_map[unit_id]:
            skipped += 1
            continue

        data = segment_map[unit_id][1]
        xliff22_target = data['target_elem']

        source_elem = trans_unit.find(f'{{{NS_XLIFF12}}}source')
        if source_elem is None:
            skipped += 1
            continue

        lookup = _build_source_tag_lookup(source_elem)
        new_content = _rebuild_txlf_target_content(xliff22_target, lookup)

        target = trans_unit.find(f'{{{NS_XLIFF12}}}target')
        if target is None:
            src_index = list(trans_unit).index(source_elem)
            target = etree.Element('{%s}target' % NS_XLIFF12)
            trans_unit.insert(src_index + 1, target)

        # Preserve non-state, non-content attributes (gs4tr:seginfo, xml:space, …)
        preserved_attrs = {k: v for k, v in target.attrib.items() if k != 'state'}

        target.clear()
        for k, v in preserved_attrs.items():
            target.set(k, v)
        target.set('state', map_xliff22_state_to_txlf(data['state']))
        _fill_element(target, new_content)

        updated += 1

    # Refresh translated-segment-count on <file> (best-effort)
    file_elem = root.find(f'{{{NS_XLIFF12}}}file')
    if file_elem is not None:
        translated = 0
        for t in root.findall(f'.//{{{NS_XLIFF12}}}target'):
            if t.get('state') in ('translated', 'signed-off', 'final'):
                translated += 1
        file_elem.set(f'{{{NS_GS4TR}}}translated-segment-count', str(translated))

    tree.write(str(output_path), encoding='utf-8', xml_declaration=True, pretty_print=False)
    return updated, skipped, total


def find_txlf_for_file_id(file_id, txlf_dir):
    """Find the TXLF file matching a XLIFF 2.2 <file id>. Strategies: exact →
    add .txlf → case-insensitive."""
    txlf_dir = Path(txlf_dir)
    exact = txlf_dir / file_id
    if exact.exists():
        return exact
    if not file_id.lower().endswith('.txlf'):
        with_ext = txlf_dir / f"{file_id}.txlf"
        if with_ext.exists():
            return with_ext
    file_id_lower = file_id.lower()
    for c in txlf_dir.iterdir():
        if c.suffix.lower() == '.txlf' and c.name.lower() == file_id_lower:
            return c
    return None


def batch_merge_xliff22_to_txlf(xliff22_path, txlf_dir, output_dir, dry_run=False):
    """Process all <file> elements in XLIFF 2.2 and merge into matching TXLFs."""
    tree = etree.parse(str(xliff22_path))
    root = tree.getroot()

    file_elements = root.findall(f'.//{{{NS_XLIFF22}}}file')
    print(f"Found {len(file_elements)} file element(s) in XLIFF 2.2")
    print("=" * 70)

    output_dir = Path(output_dir)
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for idx, file_elem in enumerate(file_elements, 1):
        file_id = file_elem.get('id')
        print(f"\n[{idx}/{len(file_elements)}] File ID: {file_id}")
        txlf_path = find_txlf_for_file_id(file_id, txlf_dir)
        if txlf_path is None:
            print(f"  ✗ No matching TXLF found")
            results.append({'file_id': file_id, 'status': 'no_match'})
            continue
        print(f"  ✓ Matched: {txlf_path.name}")

        segment_map = build_segment_map_from_file_element(file_elem)
        pending = sum(len(v) for v in segment_map.values())
        print(f"  Segments in XLIFF 2.2: {pending}")

        if dry_run:
            results.append({'file_id': file_id, 'status': 'dry_run', 'segments': pending})
            continue

        output_path = output_dir / txlf_path.name
        try:
            updated, skipped, total = update_txlf_targets(txlf_path, segment_map, output_path)
            print(f"  ✓ Updated {updated} / {total} trans-units (skipped {skipped})")
            print(f"  ✓ Written: {output_path}")
            results.append({
                'file_id': file_id, 'status': 'success',
                'txlf': str(txlf_path), 'output': str(output_path),
                'updated': updated, 'skipped': skipped, 'total': total,
            })
        except Exception as e:
            print(f"  ✗ Error: {e}")
            import traceback
            traceback.print_exc()
            results.append({'file_id': file_id, 'status': 'error', 'error': str(e)})

    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Merge XLIFF 2.2 translations back into Wordfast Pro TXLF files',
    )
    parser.add_argument('xliff22', help='XLIFF 2.2 file')
    parser.add_argument('--txlf-dir', required=True, help='Directory with original TXLF files')
    parser.add_argument('--output-dir', required=True, help='Output directory for updated TXLFs')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    xliff22 = Path(args.xliff22)
    if not xliff22.exists():
        print(f"Error: {xliff22} not found", file=sys.stderr)
        sys.exit(1)
    txlf_dir = Path(args.txlf_dir)
    if not txlf_dir.exists():
        print(f"Error: {txlf_dir} not found", file=sys.stderr)
        sys.exit(1)

    results = batch_merge_xliff22_to_txlf(xliff22, txlf_dir, args.output_dir, args.dry_run)
    success = sum(1 for r in results if r['status'] == 'success')
    no_match = sum(1 for r in results if r['status'] == 'no_match')
    errors = sum(1 for r in results if r['status'] == 'error')
    print(f"\n✓ Merged: {success}  ⚠ No match: {no_match}  ✗ Errors: {errors}")
    sys.exit(0 if not errors and not no_match else 1)


if __name__ == '__main__':
    main()
