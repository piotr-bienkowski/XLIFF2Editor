#!/usr/bin/env python3
"""
XLIFF 2.2 to Phrase (Memsource) MXLIFF Merger

Writes translations from an XLIFF 2.2 file produced by mxliff_xliff22_converter
back into the original .mxliff so it can be re-uploaded to Phrase as a
bilingual MXLIFF.

Unlike the SDLXLIFF / MQXLIFF / TXLF mergers this one is single-file in,
single-file out: a joined Phrase job keeps all of its <file> elements inside one
.mxliff, and <trans-unit> ids are unique document-wide (they carry the job's
m:task-id prefix), so they are the join key.  <group> ids are NOT unique across
a joined job and must never be used for matching.

Everything outside <target>, ``m:confirmed`` and ``m:level-edited`` is left
byte-identical, including the inline-code metadata and the CDATA preview
skeleton in the header, so Phrase accepts the file on re-import.
"""

import sys
from pathlib import Path

from lxml import etree

NS_XLIFF12 = 'urn:oasis:names:tc:xliff:document:1.2'
NS_XLIFF22 = 'urn:oasis:names:tc:xliff:document:2.0'
NS_MEMSOURCE = 'http://www.memsource.com/mxlf/2.0'
NS_XML = 'http://www.w3.org/XML/1998/namespace'
NS = {'x12': NS_XLIFF12, 'm': NS_MEMSOURCE}

# XLIFF 2.2 states that mean "the translator signed this off".
CONFIRMED_STATES = {'final', 'reviewed'}


def map_state_to_confirmed(state):
    """Map an XLIFF 2.2 segment state to Phrase's ``m:confirmed`` flag."""
    return '1' if (state or '') in CONFIRMED_STATES else '0'


# ── XLIFF 2.2 inline content → Phrase brace notation ──────────────────────────

def serialize_to_phrase(element):
    """
    Render XLIFF 2.2 inline content back as Phrase brace notation.

        <ph id="1"/>          → {1}
        <sc id="1"/>          → {1>
        <ec startRef="1"/>    → <1}
        <pc id="1">x</pc>     → {1>x<1}

    <pc> is accepted even though the converter never emits it, so a file hand-
    edited or produced by another importer still merges.
    """
    if element is None:
        return ''

    parts = [element.text or '']

    for child in element:
        tag = etree.QName(child).localname
        if tag == 'ph':
            parts.append('{%s}' % child.get('id', ''))
        elif tag == 'sc':
            parts.append('{%s>' % child.get('id', ''))
        elif tag == 'ec':
            ref = child.get('startRef') or child.get('id') or ''
            parts.append('<%s}' % ref)
        elif tag == 'pc':
            pc_id = child.get('id', '')
            parts.append('{%s>' % pc_id)
            parts.append(serialize_to_phrase(child))
            parts.append('<%s}' % pc_id)
        else:
            # Unknown inline element: keep its text, drop the wrapper.
            parts.append(serialize_to_phrase(child))
        parts.append(child.tail or '')

    return ''.join(parts)


def sync_target_metadata(trans_unit):
    """
    Make <m:tunit-target-metadata> mirror <m:tunit-metadata>.

    Phrase treats the two blocks as one declaration of the codes available to
    the unit, not as a record of which codes the target happens to use: across
    every sample examined (Phrase 2.13-2.17, 1187 metadata-bearing units) the
    target block is a verbatim copy of the source block, retaining marks the
    target dropped and keeping source order even when the target reorders them.
    So the blocks are left alone; the only action taken is recreating the target
    block if a file is missing it, which keeps a hand-edited or older .mxliff
    consistent.
    """
    source_block = trans_unit.find('m:tunit-metadata', NS)
    if source_block is None:
        return
    if trans_unit.find('m:tunit-target-metadata', NS) is not None:
        return

    mirror = etree.fromstring(etree.tostring(source_block))
    mirror.tag = '{%s}tunit-target-metadata' % NS_MEMSOURCE
    mirror.tail = source_block.tail
    source_block.addnext(mirror)


# ── segment map ───────────────────────────────────────────────────────────────

def build_segment_map(xliff22_path):
    """
    Build ``{trans_unit_id: {'target', 'state'}}`` from an XLIFF 2.2 file.

    The first <segment> of each <unit> wins: the converter emits exactly one.
    """
    tree = etree.parse(str(xliff22_path))
    root = tree.getroot()

    segment_map = {}
    for unit in root.findall(f'.//{{{NS_XLIFF22}}}unit'):
        unit_id = unit.get('id')
        if not unit_id:
            continue
        segment = unit.find(f'{{{NS_XLIFF22}}}segment')
        if segment is None:
            continue
        target = segment.find(f'{{{NS_XLIFF22}}}target')
        segment_map[unit_id] = {
            'target': serialize_to_phrase(target),
            'state': segment.get('state', ''),
        }
    return segment_map


def is_phrase_xliff(xliff22_path):
    """True when the XLIFF 2.2 file was produced by the MXLIFF importer."""
    tree = etree.parse(str(xliff22_path))
    root = tree.getroot()
    for unit in root.findall(f'.//{{{NS_XLIFF22}}}unit'):
        if unit.get('x-mxliff-origin') == 'phrase':
            return True
    return False


# ── merge ─────────────────────────────────────────────────────────────────────

def merge_xliff22_to_mxliff(xliff22_path, mxliff_path, output_path,
                            skip_locked=True, mark_edited=True):
    """
    Write translations from *xliff22_path* into *mxliff_path*, saving to
    *output_path*.

    Args:
        xliff22_path: Translated XLIFF 2.2 file.
        mxliff_path:  The original .mxliff downloaded from Phrase.
        output_path:  Where the updated .mxliff is written.
        skip_locked:  Leave segments Phrase locked untouched (default).
        mark_edited:  Set ``m:level-edited="true"`` on segments whose target
                      text actually changed, so Phrase reports them as edited
                      at this workflow level.

    Returns:
        dict with counts: updated, unchanged, locked_skipped, missing, extra.
    """
    xliff22_path = Path(xliff22_path)
    mxliff_path = Path(mxliff_path)
    output_path = Path(output_path)

    segment_map = build_segment_map(xliff22_path)

    # strip_cdata=False keeps the <m:in-ctx-preview-skel> CDATA block intact.
    parser = etree.XMLParser(strip_cdata=False, resolve_entities=False)
    tree = etree.parse(str(mxliff_path), parser)
    root = tree.getroot()

    updated = unchanged = locked_skipped = missing = 0
    seen = set()

    for trans_unit in root.findall('.//x12:trans-unit', NS):
        unit_id = trans_unit.get('id')
        if not unit_id:
            continue

        data = segment_map.get(unit_id)
        if data is None:
            missing += 1
            continue
        seen.add(unit_id)

        locked = (trans_unit.get('{%s}locked' % NS_MEMSOURCE) or '').lower() == 'true'
        if skip_locked and locked:
            locked_skipped += 1
            continue

        new_text = data['target']

        target = trans_unit.find('x12:target', NS)
        if target is None:
            source = trans_unit.find('x12:source', NS)
            index = list(trans_unit).index(source) + 1 if source is not None else 0
            target = etree.Element('{%s}target' % NS_XLIFF12)
            trans_unit.insert(index, target)
            old_text = ''
        else:
            old_text = ''.join(target.itertext())

        # clear() drops attributes and the tail whitespace that separates
        # <target> from the next element; keep both so untouched segments stay
        # byte-identical and a diff of the merged file shows only real edits.
        saved_attrib = dict(target.attrib)
        saved_tail = target.tail
        target.clear()
        target.attrib.update(saved_attrib)
        target.tail = saved_tail
        target.text = new_text or None

        trans_unit.set('{%s}confirmed' % NS_MEMSOURCE,
                       map_state_to_confirmed(data['state']))

        sync_target_metadata(trans_unit)

        if old_text == new_text:
            unchanged += 1
        else:
            if mark_edited:
                trans_unit.set('{%s}level-edited' % NS_MEMSOURCE, 'true')
            updated += 1

    extra = len(segment_map) - len(seen)

    tree.write(str(output_path), encoding='UTF-8', xml_declaration=True,
               pretty_print=False)

    return {
        'updated': updated,
        'unchanged': unchanged,
        'locked_skipped': locked_skipped,
        'missing': missing,
        'extra': extra,
        'output_path': str(output_path),
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description='Merge XLIFF 2.2 translations back into a Phrase MXLIFF file',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  %(prog)s translated.xlf --mxliff original.mxliff -o updated.mxliff
        """
    )
    parser.add_argument('xliff22', help='Translated XLIFF 2.2 file')
    parser.add_argument('--mxliff', required=True, help='Original .mxliff from Phrase')
    parser.add_argument('-o', '--output', required=True, help='Output .mxliff path')
    parser.add_argument('--include-locked', action='store_true',
                        help='Also write into segments locked in Phrase')
    parser.add_argument('--no-mark-edited', action='store_true',
                        help='Do not set m:level-edited on changed segments')
    args = parser.parse_args()

    for path in (args.xliff22, args.mxliff):
        if not Path(path).exists():
            print(f'Error: {path} not found', file=sys.stderr)
            sys.exit(1)

    try:
        result = merge_xliff22_to_mxliff(
            args.xliff22, args.mxliff, args.output,
            skip_locked=not args.include_locked,
            mark_edited=not args.no_mark_edited,
        )
    except Exception as e:
        print(f'✗ Error: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"✓ Updated:        {result['updated']}")
    print(f"  Unchanged:      {result['unchanged']}")
    if result['locked_skipped']:
        print(f"  Locked, kept:   {result['locked_skipped']}")
    if result['missing']:
        print(f"  ⚠ Not in XLIFF: {result['missing']}")
    if result['extra']:
        print(f"  ⚠ Unmatched:    {result['extra']}")
    print(f"✓ Written to: {result['output_path']}")
    sys.exit(0)


if __name__ == '__main__':
    main()
