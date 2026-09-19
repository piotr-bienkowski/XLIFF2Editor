#!/usr/bin/env python3
"""
Phrase (Memsource) MXLIFF to XLIFF 2.2 Converter Module

MXLIFF is XLIFF 1.2 carrying the Memsource extension namespace
``http://www.memsource.com/mxlf/2.0`` (conventional prefix ``m``).  It differs
from every other bilingual format this editor supports in three ways:

1. **No XLIFF 1.2 inline elements.**  There is no bpt/ept/ph/x/g inside
   <source>/<target>; inline codes are written into the *text* with Phrase's
   brace notation:

       {1}            standalone code
       {1>text<1}     paired code with content (numeric id)
       {b>text<b}     paired intrinsic formatting code (letter id: b, i, u, …)

   Paired codes nest.  The numeric ids reference <m:mark> entries in
   <m:tunit-metadata>; letter ids are intrinsic and have no metadata entry.

2. **Joined jobs.**  One .mxliff may hold many <file> elements, each with its
   own <body>.  <group> ids restart at 0 in every file and therefore collide
   across the document; <trans-unit> ids are prefixed with the job's
   ``m:task-id`` and are unique document-wide.  Only trans-unit ids are safe
   keys.

3. **Attribute order varies by Phrase version** (m:version 2.13 … 2.17), so the
   file must be read with an XML parser, never by pattern matching.

Segment status lives in ``m:confirmed`` / ``m:locked`` on <trans-unit>; match
provenance in ``m:score`` (1.01 = 101% context match) and ``m:trans-origin``.

Can be used as a standalone script or imported as a module.
"""

import re
import sys
from pathlib import Path

from lxml import etree

NS_XLIFF12 = 'urn:oasis:names:tc:xliff:document:1.2'
NS_XLIFF22 = 'urn:oasis:names:tc:xliff:document:2.0'
NS_MEMSOURCE = 'http://www.memsource.com/mxlf/2.0'
NS_XML = 'http://www.w3.org/XML/1998/namespace'
NS = {'x12': NS_XLIFF12, 'm': NS_MEMSOURCE}

# Phrase inline-code notation.  Ordered so that the two-character openers and
# closers are tried before the standalone form.
TAG_RE = re.compile(r'\{(\w+)>|<(\w+)\}|\{(\d+)\}')


# ── status / match mapping ────────────────────────────────────────────────────

def map_mxliff_state(confirmed, has_target):
    """Map ``m:confirmed`` to an XLIFF 2.2 segment state."""
    if str(confirmed) == '1':
        return 'final'
    return 'translated' if has_target else 'initial'


def compute_match_label(score, origin):
    """Short display label for the Match column ('CM', '100%', '87%', 'MT', …)."""
    origin = (origin or '').lower()
    try:
        value = float(score)
    except (TypeError, ValueError):
        value = None

    if origin in ('mt', 'nmt'):
        return 'MT'
    if origin == 'tm' and value is not None:
        if value >= 1.005:          # Phrase writes 1.01 for a 101% context match
            return 'CM'
        if value <= 0:
            return ''
        return f'{int(round(value * 100))}%'
    if origin == 'tm':
        return 'TM'
    if origin:
        return origin.upper()
    return ''


def score_to_percent(score):
    """Render ``m:score`` as an integer percent string, or '' when unusable."""
    try:
        value = float(score)
    except (TypeError, ValueError):
        return ''
    if value <= 0:
        return ''
    return str(int(round(value * 100)))


# ── Phrase brace notation ─────────────────────────────────────────────────────

def parse_phrase_tags(text):
    """
    Split Phrase brace notation into a flat token list.

    Returns a list of ``str`` (literal text) and ``(kind, tag_id)`` tuples where
    *kind* is 'ph' (standalone), 'sc' (paired open) or 'ec' (paired close).
    Text that does not match the notation is left verbatim, so a stray '{' or a
    literal '}' survives untouched.
    """
    if not text:
        return []

    tokens = []
    pos = 0
    for match in TAG_RE.finditer(text):
        if match.start() > pos:
            tokens.append(text[pos:match.start()])
        open_id, close_id, standalone_id = match.groups()
        if standalone_id is not None:
            tokens.append(('ph', standalone_id))
        elif open_id is not None:
            tokens.append(('sc', open_id))
        else:
            tokens.append(('ec', close_id))
        pos = match.end()
    if pos < len(text):
        tokens.append(text[pos:])
    return tokens


def _fill_element(elem, parts):
    for part in parts:
        if isinstance(part, str):
            if len(elem):
                elem[-1].tail = (elem[-1].tail or '') + part
            else:
                elem.text = (elem.text or '') + part
        else:
            elem.append(part)


def build_xliff22_content(text, marks=None):
    """
    Convert Phrase brace text to a list of strings / XLIFF 2.2 inline elements.

    Paired codes become the flat ``<sc>`` / ``<ec>`` pair rather than a nested
    ``<pc>``: Phrase's own model is flat, paired codes may nest three deep, and
    the editor's grid renders nested <pc> ambiguously.  Flat codes round-trip
    byte-for-byte and stay editable.

    Only the mark's short ``type`` is copied onto the element.  Its ``content``
    (the original DOCX/DITA markup, often hundreds of characters) is deliberately
    left behind: it stays in the .mxliff the merger reads, and carrying it here
    would bloat every segment and be echoed back into each edited target.

    Args:
        text:  The already-unescaped text content of <source> or <target>.
        marks: Optional ``{mark_id: {'type': str, 'content': str}}`` from
               <m:tunit-metadata>, used to annotate the generated elements.
    """
    marks = marks or {}
    parts = []

    for token in parse_phrase_tags(text):
        if isinstance(token, str):
            parts.append(token)
            continue

        kind, tag_id = token
        info = marks.get(tag_id, {})

        if kind == 'ec':
            elem = etree.Element('{%s}ec' % NS_XLIFF22)
            elem.set('startRef', tag_id)
        else:
            elem = etree.Element('{%s}%s' % (NS_XLIFF22, kind))
            elem.set('id', tag_id)
            if info.get('type'):
                elem.set('type', info['type'])
        parts.append(elem)

    return parts


def read_marks(trans_unit, tag_name='tunit-metadata'):
    """Read ``{mark_id: {'type', 'content'}}`` from a metadata block."""
    marks = {}
    block = trans_unit.find('m:%s' % tag_name, NS)
    if block is None:
        return marks
    for mark in block.findall('m:mark', NS):
        mark_id = mark.get('id')
        if not mark_id:
            continue
        type_elem = mark.find('m:type', NS)
        content_elem = mark.find('m:content', NS)
        marks[mark_id] = {
            'type': (type_elem.text or '') if type_elem is not None else '',
            'content': (content_elem.text or '') if content_elem is not None else '',
        }
    return marks


# ── conversion ────────────────────────────────────────────────────────────────

def _text_of(elem):
    """Full text of a <source>/<target>; entities are already unescaped."""
    if elem is None:
        return ''
    return ''.join(elem.itertext())


def process_mxliff_file(input_path, segment_counter=0, skip_locked=False):
    """
    Process one .mxliff document (which may contain several <file> elements).

    Returns:
        tuple: (list_of_file22_elements, new_segment_counter, src_lang, trg_lang)
    """
    tree = etree.parse(str(input_path))
    root = tree.getroot()

    file_elems = root.findall('.//x12:file', NS)
    if not file_elems:
        raise ValueError('No <file> element found — is this a Phrase MXLIFF?')

    source_lang = file_elems[0].get('source-language', 'und')
    target_lang = file_elems[0].get('target-language', '')

    # <file original="..."> repeats across joined jobs; disambiguate with the
    # job's task-id so the editor's File column stays meaningful.
    seen_names = {}
    for file_elem in file_elems:
        name = file_elem.get('original') or file_elem.get('m:task-id') or 'file'
        seen_names[name] = seen_names.get(name, 0) + 1

    used_names = {}
    files22 = []

    for file_elem in file_elems:
        original = file_elem.get('original') or ''
        task_id = file_elem.get('{%s}task-id' % NS_MEMSOURCE) or ''
        name = original or task_id or 'file'
        if seen_names.get(name, 0) > 1:
            used_names[name] = used_names.get(name, 0) + 1
            file_id = f'{name} [{task_id or used_names[name]}]'
        else:
            file_id = name

        file22 = etree.Element('{%s}file' % NS_XLIFF22, id=file_id)
        if original:
            file22.set('original', original)
        if task_id:
            file22.set('x-mxliff-task-id', task_id)

        for trans_unit in file_elem.findall('.//x12:trans-unit', NS):
            unit_id = trans_unit.get('id')
            if not unit_id:
                continue

            source_elem = trans_unit.find('x12:source', NS)
            if source_elem is None:
                continue
            source_text = _text_of(source_elem)
            if not source_text.strip():
                continue

            locked = (trans_unit.get('{%s}locked' % NS_MEMSOURCE) or '').lower() == 'true'
            if skip_locked and locked:
                continue

            target_elem = trans_unit.find('x12:target', NS)
            target_text = _text_of(target_elem)

            segment_counter += 1

            unit22 = etree.SubElement(file22, '{%s}unit' % NS_XLIFF22, id=unit_id)
            # Provenance: lets the merger verify the XLIFF came from this format
            # and lets a reviewer trace a row back to the Phrase job.
            unit22.set('x-mxliff-origin', 'phrase')
            group = trans_unit.getparent()
            if group is not None and etree.QName(group).localname == 'group':
                if group.get('id') is not None:
                    unit22.set('x-mxliff-group', group.get('id'))
            para_id = trans_unit.get('{%s}para-id' % NS_MEMSOURCE)
            if para_id is not None:
                unit22.set('x-mxliff-para-id', para_id)

            score = trans_unit.get('{%s}score' % NS_MEMSOURCE)
            origin = trans_unit.get('{%s}trans-origin' % NS_MEMSOURCE)
            confirmed = trans_unit.get('{%s}confirmed' % NS_MEMSOURCE)

            seg_attrs = {'id': str(segment_counter)}
            seg_attrs['state'] = map_mxliff_state(confirmed, bool(target_text.strip()))
            if locked:
                seg_attrs['translate'] = 'no'

            label = compute_match_label(score, origin)
            if label:
                seg_attrs['match'] = label
            if origin:
                seg_attrs['match-origin'] = origin
            percent = score_to_percent(score)
            if percent:
                seg_attrs['match-percent'] = percent
            origin_detail = trans_unit.get('{%s}trans-origin-detail' % NS_MEMSOURCE)
            if origin_detail:
                seg_attrs['match-system'] = origin_detail

            segment22 = etree.SubElement(unit22, '{%s}segment' % NS_XLIFF22, **seg_attrs)

            source_marks = read_marks(trans_unit, 'tunit-metadata')
            target_marks = read_marks(trans_unit, 'tunit-target-metadata') or source_marks

            source22 = etree.SubElement(segment22, '{%s}source' % NS_XLIFF22)
            source22.set('{%s}space' % NS_XML, 'preserve')
            _fill_element(source22, build_xliff22_content(source_text, source_marks))

            target22 = etree.SubElement(segment22, '{%s}target' % NS_XLIFF22)
            target22.set('{%s}space' % NS_XML, 'preserve')
            if target_text:
                _fill_element(target22, build_xliff22_content(target_text, target_marks))

        if len(file22):
            files22.append(file22)

    return files22, segment_counter, source_lang, target_lang


def convert_mxliff_to_xliff22(input_paths, output_path, verbose=True, skip_locked=False):
    """
    Convert one or more Phrase MXLIFF files to a single XLIFF 2.2 file.

    Args:
        input_paths: List of Path objects or strings pointing to MXLIFF files.
        output_path: Path object or string for the output XLIFF 2.2 file.
        verbose:     If True, print progress messages.
        skip_locked: If True, omit segments Phrase has locked.

    Returns:
        dict: Statistics about the conversion.
    """
    if not input_paths:
        raise ValueError('No input files provided')

    input_paths = [Path(p) for p in input_paths]
    output_path = Path(output_path)

    first_files, _, source_lang, target_lang = process_mxliff_file(
        input_paths[0], 0, skip_locked
    )

    xliff22_root = etree.Element(
        '{%s}xliff' % NS_XLIFF22,
        version='2.2',
        srcLang=source_lang,
        nsmap={
            None: NS_XLIFF22,
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
        },
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
            print(f'Processing {idx}/{len(input_paths)}: {input_path.name}')

        files22, segment_counter, _, _ = process_mxliff_file(
            input_path, segment_counter, skip_locked
        )

        segs_here = 0
        for file22 in files22:
            xliff22_root.append(file22)
            segs_here += len(file22.findall('.//{%s}segment' % NS_XLIFF22))

        total_segments += segs_here
        processed_files.append({
            'filename': input_path.name,
            'units': segs_here,
            'segments': segs_here,
            'internal_files': len(files22),
        })
        if verbose:
            if segs_here:
                print(f'  ✓ Added {segs_here} segments from {len(files22)} internal file(s)')
            else:
                print('  ⚠ Skipped (no valid segments)')

    etree.ElementTree(xliff22_root).write(
        str(output_path), encoding='utf-8', xml_declaration=True, pretty_print=False
    )

    if verbose:
        print(f'\n✓ Converted {total_segments} total segments from {len(input_paths)} file(s)')
        print(f'✓ Output written to: {output_path}')

    return {
        'total_segments': total_segments,
        'total_files': len(processed_files),
        'files': processed_files,
        'output_path': str(output_path),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Convert Phrase (Memsource) MXLIFF to XLIFF 2.2',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s job.mxliff -o job.xlf
  %(prog)s *.mxliff -o merged.xlf --skip-locked
        """
    )
    parser.add_argument('input', nargs='+', help='Input MXLIFF file(s)')
    parser.add_argument('-o', '--output', required=True, help='Output XLIFF 2.2 file')
    parser.add_argument('--skip-locked', action='store_true',
                        help='Omit segments locked in Phrase')
    parser.add_argument('-q', '--quiet', action='store_true', help='Suppress progress messages')
    args = parser.parse_args()

    input_paths = [Path(p) for p in args.input if Path(p).exists()]
    if not input_paths:
        print('Error: No valid input files found', file=sys.stderr)
        sys.exit(1)

    try:
        convert_mxliff_to_xliff22(input_paths, Path(args.output),
                                  verbose=not args.quiet, skip_locked=args.skip_locked)
        sys.exit(0)
    except Exception as e:
        print(f'\n✗ Error: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
