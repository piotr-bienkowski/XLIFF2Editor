#!/usr/bin/env python3
"""
Wordfast Pro TXLF to XLIFF 2.2 Converter Module

TXLF is XLIFF 1.2 with GS4TR extensions. Inline tag conventions:
  bx / ex  — paired split, self-closing, matched by @rid
  bpt/ept  — paired split with content (formatting XML), matched by @rid
  ph       — unpaired standalone with content
  x        — unpaired self-closing
  g        — paired wrapping

Can be used as a standalone script or imported as a module.
"""

import sys
from pathlib import Path
from lxml import etree

NS_XLIFF12 = 'urn:oasis:names:tc:xliff:document:1.2'
NS_XLIFF22 = 'urn:oasis:names:tc:xliff:document:2.0'
NS_XML = 'http://www.w3.org/XML/1998/namespace'
NS = {'x12': NS_XLIFF12}

TXLF_STATE_MAP = {
    '':                            'initial',
    'needs-translation':           'initial',
    'new':                         'initial',
    'translated':                  'translated',
    'needs-review-translation':    'needs-review-translation',
    'signed-off':                  'final',
    'final':                       'final',
}


def map_txlf_state(state):
    if state is None:
        return 'initial'
    return TXLF_STATE_MAP.get(state, 'translated')


def _fill_element(elem, parts):
    for part in parts:
        if isinstance(part, str):
            if len(elem):
                elem[-1].tail = (elem[-1].tail or '') + part
            else:
                elem.text = (elem.text or '') + part
        else:
            elem.append(part)


def _make_pc(pc_id, ctype=None):
    pc = etree.Element('{%s}pc' % NS_XLIFF22)
    if pc_id is not None:
        pc.set('id', str(pc_id))
    if ctype:
        pc.set('type', ctype)
    return pc


def _make_ph(ph_id, ctype=None):
    ph = etree.Element('{%s}ph' % NS_XLIFF22)
    if ph_id is not None:
        ph.set('id', str(ph_id))
    if ctype:
        ph.set('type', ctype)
    return ph


def _convert_single(element):
    """Convert a single element (used inside a pc's content walk) to a list of
    strings/elements in XLIFF 2.2 form. bx/ex/bpt/ept are handled at the
    sibling-pairing level in extract_content_to_xliff22 (not here)."""
    tag = etree.QName(element).localname
    if tag in ('ph', 'x'):
        return [_make_ph(element.get('id'), element.get('ctype'))]
    if tag == 'g':
        pc = _make_pc(element.get('id'), element.get('ctype'))
        _fill_element(pc, extract_content_to_xliff22(element))
        return [pc]
    if tag == 'mrk':
        return extract_content_to_xliff22(element)
    if tag in ('bx', 'ex', 'bpt', 'ept'):
        # Shouldn't be nested inside a g; if it is, emit a marker ph to preserve id
        rid = element.get('rid') or element.get('id')
        return [_make_ph(rid, element.get('ctype'))]
    # Unknown: try generic passthrough
    new = etree.Element(element.tag)
    new.attrib.update({k: v for k, v in element.attrib.items() if '{' not in k})
    _fill_element(new, extract_content_to_xliff22(element))
    return [new]


def extract_content_to_xliff22(element):
    """Convert TXLF source/target content to a list of strings and XLIFF 2.2
    elements. Pairs bx/ex and bpt/ept by @rid into <pc>."""
    result = []
    if element.text:
        result.append(element.text)

    children = list(element)
    i = 0
    while i < len(children):
        child = children[i]
        tag = etree.QName(child).localname

        if tag == 'bx':
            rid = child.get('rid') or child.get('id')
            pc = _make_pc(rid, child.get('ctype'))
            pc_parts = []
            if child.tail:
                pc_parts.append(child.tail)
            i += 1
            close_tail = None
            while i < len(children):
                sib = children[i]
                sib_tag = etree.QName(sib).localname
                if sib_tag == 'ex' and (sib.get('rid') == rid or sib.get('id') == rid):
                    close_tail = sib.tail
                    i += 1
                    break
                pc_parts.extend(_convert_single(sib))
                if sib.tail:
                    pc_parts.append(sib.tail)
                i += 1
            _fill_element(pc, pc_parts)
            result.append(pc)
            if close_tail:
                result.append(close_tail)

        elif tag == 'bpt':
            rid = child.get('rid') or child.get('id')
            pc = _make_pc(rid, child.get('ctype'))
            pc_parts = []
            if child.tail:
                pc_parts.append(child.tail)
            i += 1
            close_tail = None
            while i < len(children):
                sib = children[i]
                sib_tag = etree.QName(sib).localname
                if sib_tag == 'ept' and (sib.get('rid') == rid or sib.get('id') == rid):
                    close_tail = sib.tail
                    i += 1
                    break
                pc_parts.extend(_convert_single(sib))
                if sib.tail:
                    pc_parts.append(sib.tail)
                i += 1
            _fill_element(pc, pc_parts)
            result.append(pc)
            if close_tail:
                result.append(close_tail)

        elif tag in ('ex', 'ept'):
            # Orphaned closing — skip element but preserve tail
            if child.tail:
                result.append(child.tail)
            i += 1

        elif tag in ('ph', 'x'):
            result.append(_make_ph(child.get('id'), child.get('ctype')))
            if child.tail:
                result.append(child.tail)
            i += 1

        elif tag == 'g':
            pc = _make_pc(child.get('id'), child.get('ctype'))
            _fill_element(pc, extract_content_to_xliff22(child))
            result.append(pc)
            if child.tail:
                result.append(child.tail)
            i += 1

        elif tag == 'mrk':
            result.extend(extract_content_to_xliff22(child))
            if child.tail:
                result.append(child.tail)
            i += 1

        else:
            # Unknown element — preserve structure (strip namespaced attrs)
            new = etree.Element(child.tag)
            new.attrib.update({k: v for k, v in child.attrib.items() if '{' not in k})
            _fill_element(new, extract_content_to_xliff22(child))
            result.append(new)
            if child.tail:
                result.append(child.tail)
            i += 1

    return result


def process_txlf_file(input_path, file_id, segment_counter=0):
    """Process a single TXLF file. Returns (file22_element, new_counter, src_lang, trg_lang)."""
    tree = etree.parse(input_path)
    root = tree.getroot()

    file_elem = root.find(f'{{{NS_XLIFF12}}}file')
    source_lang = file_elem.get('source-language', 'en') if file_elem is not None else 'en'
    target_lang = file_elem.get('target-language', '') if file_elem is not None else ''

    file22 = etree.Element('{%s}file' % NS_XLIFF22, id=file_id)

    for tu in root.findall(f'.//{{{NS_XLIFF12}}}trans-unit'):
        if tu.get('translate') == 'no':
            continue

        unit_id = tu.get('id', f'unit_{segment_counter}')
        source_elem = tu.find(f'{{{NS_XLIFF12}}}source')
        if source_elem is None:
            continue
        source_text = ''.join(source_elem.itertext()).strip()
        if not source_text:
            continue

        target_elem = tu.find(f'{{{NS_XLIFF12}}}target')
        state_raw = target_elem.get('state') if target_elem is not None else None
        xliff22_state = map_txlf_state(state_raw)

        segment_counter += 1
        unit22 = etree.SubElement(file22, '{%s}unit' % NS_XLIFF22, id=unit_id)
        seg_attrs = {'id': str(segment_counter)}
        if xliff22_state:
            seg_attrs['state'] = xliff22_state
        segment22 = etree.SubElement(unit22, '{%s}segment' % NS_XLIFF22, **seg_attrs)

        source22 = etree.SubElement(segment22, '{%s}source' % NS_XLIFF22)
        source22.set('{%s}space' % NS_XML, 'preserve')
        _fill_element(source22, extract_content_to_xliff22(source_elem))

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


def convert_txlf_to_xliff22(input_paths, output_path, verbose=True):
    """Convert one or more TXLF files to a single XLIFF 2.2 file."""
    if not input_paths:
        raise ValueError("No input files provided")

    input_paths = [Path(p) for p in input_paths]
    output_path = Path(output_path)

    first_tree = etree.parse(str(input_paths[0]))
    first_file = first_tree.getroot().find(f'{{{NS_XLIFF12}}}file')
    source_lang = first_file.get('source-language', 'en') if first_file is not None else 'en'
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
        file22, segment_counter, _, _ = process_txlf_file(
            str(input_path), file_id, segment_counter
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
        str(output_path), encoding='utf-8', xml_declaration=True, pretty_print=False
    )

    if verbose:
        print(f"\n✓ Converted {total_segments} segments from {len(input_paths)} file(s)")
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
        description='Convert Wordfast Pro TXLF to XLIFF 2.2 (supports multiple input files)',
    )
    parser.add_argument('input', nargs='+', help='Input TXLF file(s)')
    parser.add_argument('-o', '--output', required=True, help='Output XLIFF 2.2 file')
    parser.add_argument('-q', '--quiet', action='store_true', help='Suppress progress messages')
    args = parser.parse_args()

    input_paths = [Path(p) for p in args.input if Path(p).exists()]
    if not input_paths:
        print("Error: No valid input files found", file=sys.stderr)
        sys.exit(1)

    try:
        convert_txlf_to_xliff22(input_paths, Path(args.output), verbose=not args.quiet)
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
