#!/usr/bin/env python3
"""
memoQ MQXLIFF to XLIFF 2.2 Converter Module
Can be used as a standalone script or imported as a module.
"""

import sys
from pathlib import Path
from lxml import etree

NS = {'xliff12': 'urn:oasis:names:tc:xliff:document:1.2'}
NS_XLIFF12 = 'urn:oasis:names:tc:xliff:document:1.2'
NS_XLIFF22 = 'urn:oasis:names:tc:xliff:document:2.0'
NS_XML = 'http://www.w3.org/XML/1998/namespace'

MQ_STATUS_MAP = {
    'NotStarted':             'initial',
    'PreTranslated':          'translated',
    'PartiallyEdited':        'translated',
    'ManuallyConfirmed':      'final',
    'AssembledFromFragments': 'translated',
    'AutoJoined':             'translated',
    'AutoSplit':              'initial',
    'AutoSplitAndEmpty':      'initial',
    'Ackknowledged':          'reviewed',   # schema typo preserved
}


def map_mq_status(mq_status):
    if not mq_status:
        return None
    return MQ_STATUS_MAP.get(mq_status, 'initial')


def _fill_element(elem, parts):
    for part in parts:
        if isinstance(part, str):
            if len(elem):
                elem[-1].tail = (elem[-1].tail or '') + part
            else:
                elem.text = (elem.text or '') + part
        else:
            elem.append(part)


def extract_content_to_xliff22(element):
    """
    Convert XLIFF 1.2 source/target content to a list of strings and XLIFF 2.2 elements.
    Handles bpt/ept pairs (flat siblings) and nested g/ph/x/it tags.
    """
    result = []

    if element.text:
        result.append(element.text)

    children = list(element)
    i = 0
    while i < len(children):
        child = children[i]
        tag = etree.QName(child).localname

        if tag == 'bpt':
            bpt_id = child.get('id', str(i))
            pc = etree.Element('{%s}pc' % NS_XLIFF22)
            pc.set('id', bpt_id)
            if 'ctype' in child.attrib:
                pc.set('type', child.get('ctype'))

            # Content is bpt.tail + subsequent siblings until matching ept
            pc_parts = []
            if child.tail:
                pc_parts.append(child.tail)

            i += 1
            ept_tail = None
            while i < len(children):
                sibling = children[i]
                sibling_tag = etree.QName(sibling).localname
                if sibling_tag == 'ept' and sibling.get('id') == bpt_id:
                    ept_tail = sibling.tail
                    i += 1
                    break
                else:
                    nested = _convert_node(sibling)
                    pc_parts.extend(nested)
                    if sibling.tail:
                        pc_parts.append(sibling.tail)
                    i += 1

            _fill_element(pc, pc_parts)
            result.append(pc)
            if ept_tail:
                result.append(ept_tail)

        elif tag == 'ept':
            # Orphaned ept — should not happen; preserve any tail text
            if child.tail:
                result.append(child.tail)
            i += 1

        elif tag == 'g':
            pc = etree.Element('{%s}pc' % NS_XLIFF22)
            if 'id' in child.attrib:
                pc.set('id', child.get('id'))
            _fill_element(pc, extract_content_to_xliff22(child))
            result.append(pc)
            if child.tail:
                result.append(child.tail)
            i += 1

        elif tag in ('ph', 'x', 'it'):
            ph = etree.Element('{%s}ph' % NS_XLIFF22)
            if 'id' in child.attrib:
                ph.set('id', child.get('id'))
            if child.text:
                ph.text = child.text
            result.append(ph)
            if child.tail:
                result.append(child.tail)
            i += 1

        elif tag == 'mrk':
            # Unwrap mrk, keep content
            inner = extract_content_to_xliff22(child)
            result.extend(inner)
            if child.tail:
                result.append(child.tail)
            i += 1

        else:
            new = etree.Element(child.tag)
            new.attrib.update(child.attrib)
            _fill_element(new, extract_content_to_xliff22(child))
            result.append(new)
            if child.tail:
                result.append(child.tail)
            i += 1

    return result


def _convert_node(element):
    """Convert a single XLIFF 1.2 element (not bpt/ept) to XLIFF 2.2."""
    tag = etree.QName(element).localname
    if tag == 'g':
        pc = etree.Element('{%s}pc' % NS_XLIFF22)
        if 'id' in element.attrib:
            pc.set('id', element.get('id'))
        _fill_element(pc, extract_content_to_xliff22(element))
        return [pc]
    elif tag in ('ph', 'x', 'it'):
        ph = etree.Element('{%s}ph' % NS_XLIFF22)
        if 'id' in element.attrib:
            ph.set('id', element.get('id'))
        if element.text:
            ph.text = element.text
        return [ph]
    else:
        new = etree.Element(element.tag)
        new.attrib.update(element.attrib)
        _fill_element(new, extract_content_to_xliff22(element))
        return [new]


def process_mqxliff_file(input_path, file_id, segment_counter=0):
    """
    Process a single MQXLIFF file and return the XLIFF 2.2 file element.

    Returns:
        tuple: (file_element, new_segment_counter, source_lang, target_lang)
    """
    tree = etree.parse(input_path)
    root = tree.getroot()

    file_elem = root.find('.//xliff12:file', NS)
    source_lang = file_elem.get('source-language', 'und') if file_elem is not None else 'und'
    target_lang = file_elem.get('target-language', '') if file_elem is not None else ''

    file22 = etree.Element('{%s}file' % NS_XLIFF22, id=file_id)

    for trans_unit in root.findall('.//xliff12:trans-unit', NS):
        if trans_unit.get('translate') == 'no':
            continue

        unit_id = trans_unit.get('id', f'unit_{segment_counter}')

        source_elem = trans_unit.find('xliff12:source', NS)
        if source_elem is None:
            continue
        source_text = ''.join(source_elem.itertext()).strip()
        if not source_text:
            continue

        mq_ns = 'MQXliff'
        mq_status = trans_unit.get(f'{{{mq_ns}}}status')

        segment_counter += 1
        unit22 = etree.SubElement(file22, '{%s}unit' % NS_XLIFF22, id=unit_id)
        seg_attrs = {'id': str(segment_counter)}
        xliff22_state = map_mq_status(mq_status)
        if xliff22_state:
            seg_attrs['state'] = xliff22_state
        segment22 = etree.SubElement(unit22, '{%s}segment' % NS_XLIFF22, **seg_attrs)

        source22 = etree.SubElement(segment22, '{%s}source' % NS_XLIFF22)
        source22.set('{%s}space' % NS_XML, 'preserve')
        _fill_element(source22, extract_content_to_xliff22(source_elem))

        target_elem = trans_unit.find('xliff12:target', NS)
        if target_elem is not None:
            target_text = ''.join(target_elem.itertext()).strip()
            if target_text:
                target22 = etree.SubElement(segment22, '{%s}target' % NS_XLIFF22)
                target22.set('{%s}space' % NS_XML, 'preserve')
                _fill_element(target22, extract_content_to_xliff22(target_elem))

    # Remove empty units
    for unit in list(file22.findall('{%s}unit' % NS_XLIFF22)):
        if not len(unit):
            file22.remove(unit)

    return file22, segment_counter, source_lang, target_lang


def convert_mqxliff_to_xliff22(input_paths, output_path, verbose=True):
    """
    Convert one or more MQXLIFF files to a single XLIFF 2.2 file.

    Args:
        input_paths: List of Path objects or strings pointing to MQXLIFF files
        output_path: Path object or string for output XLIFF 2.2 file
        verbose: If True, print progress messages

    Returns:
        dict: Statistics about the conversion
    """
    if not input_paths:
        raise ValueError("No input files provided")

    input_paths = [Path(p) for p in input_paths]
    output_path = Path(output_path)

    first_tree = etree.parse(input_paths[0])
    first_file = first_tree.getroot().find('.//xliff12:file', NS)
    source_lang = first_file.get('source-language', 'und') if first_file is not None else 'und'
    target_lang = first_file.get('target-language', '') if first_file is not None else ''

    xliff22_root = etree.Element(
        '{%s}xliff' % NS_XLIFF22,
        version='2.2',
        srcLang=source_lang,
        nsmap={
            None: NS_XLIFF22,
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            'xml': NS_XML,
        }
    )
    if target_lang:
        xliff22_root.set('trgLang', target_lang)
    xliff22_root.set(
        '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation',
        'urn:oasis:names:tc:xliff:document:2.0 '
        'https://docs.oasis-open.org/xliff/xliff-core/v2.1/os/schemas/xliff_core_2.0.xsd'
    )

    segment_counter = 0
    total_segments = 0
    processed_files = []

    for idx, input_path in enumerate(input_paths, start=1):
        if verbose:
            print(f"Processing {idx}/{len(input_paths)}: {input_path.name}")

        file_id = input_path.name
        file22, segment_counter, src_lang, trg_lang = process_mqxliff_file(
            input_path, file_id, segment_counter
        )

        units = file22.findall('{%s}unit' % NS_XLIFF22)
        if units:
            xliff22_root.append(file22)
            segs = len(file22.findall('.//{%s}segment' % NS_XLIFF22))
            total_segments += segs
            processed_files.append({'filename': input_path.name, 'units': len(units), 'segments': segs})
            if verbose:
                print(f"  ✓ Added {len(units)} units with {segs} segments")
        else:
            if verbose:
                print(f"  ⚠ Skipped (no valid segments)")

    etree.ElementTree(xliff22_root).write(
        output_path, encoding='utf-8', xml_declaration=True, pretty_print=False
    )

    if verbose:
        print(f"\n✓ Converted {total_segments} total segments from {len(input_paths)} file(s)")
        print(f"✓ Output written to: {output_path}")

    return {
        'total_segments': total_segments,
        'total_files': len(processed_files),
        'files': processed_files,
        'output_path': str(output_path),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Convert memoQ MQXLIFF to XLIFF 2.2 (supports multiple input files)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s input.mqxliff -o output.xlf
  %(prog)s *.mqxliff -o merged.xlf
        """
    )
    parser.add_argument('input', nargs='+', help='Input MQXLIFF file(s)')
    parser.add_argument('-o', '--output', required=True, help='Output XLIFF 2.2 file')
    parser.add_argument('-q', '--quiet', action='store_true', help='Suppress progress messages')
    args = parser.parse_args()

    input_paths = [Path(p) for p in args.input if Path(p).exists()]
    if not input_paths:
        print("Error: No valid input files found", file=sys.stderr)
        sys.exit(1)

    try:
        convert_mqxliff_to_xliff22(input_paths, Path(args.output), verbose=not args.quiet)
        sys.exit(0)
    except Exception as e:
        print(f"\n✗ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
