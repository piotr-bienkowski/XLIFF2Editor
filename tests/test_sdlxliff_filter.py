"""Tests for the SDLXLIFF -> XLIFF 2.2 -> SDLXLIFF round-trip."""

import sys
import tempfile
from pathlib import Path
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sdlxliff_xliff22_converter import convert_sdlxliff_to_xliff22
from xliff22_to_sdlxliff_batch_merger import (
    build_segment_map_from_file_element,
    build_target_mrk_skeleton,
    update_sdlxliff_targets,
)

NS12 = 'urn:oasis:names:tc:xliff:document:1.2'
NS22 = 'urn:oasis:names:tc:xliff:document:2.0'
NSSDL = 'http://sdl.com/FileTypes/SdlXliff/1.0'
NS12_MAP = {'xliff12': NS12, 'sdl': NSSDL}


def _sdlxliff(body):
    return f"""<?xml version="1.0" encoding="utf-8"?>
<xliff xmlns="{NS12}" xmlns:sdl="{NSSDL}" version="1.2">
<file source-language="en-US" target-language="pl-PL" original="x.docx"
      datatype="x-sdlfilterframework2"><body>{body}</body></file></xliff>"""


# A file segmented by Studio but never pre-translated: no <target> anywhere.
NOT_PRETRANSLATED = _sdlxliff("""
<trans-unit id="u1">
<source><g id="1">Hello world.</g> Second sentence.</source>
<seg-source><mrk mtype="seg" mid="0"><g id="1">Hello world.</g></mrk> <mrk mtype="seg" mid="1">Second sentence.</mrk></seg-source>
<sdl:seg-defs><sdl:seg id="0"/><sdl:seg id="1"/></sdl:seg-defs>
</trans-unit>
<trans-unit id="u2"><source>Unsegmented unit.</source></trans-unit>""")

# A segmented unit whose first segment holds only a placeholder, so the
# converter drops it and positional mapping would be off by one.
TAG_ONLY_SEGMENT = _sdlxliff("""
<trans-unit id="b">
<source><x id="5"/>Real sentence.</source>
<seg-source><mrk mtype="seg" mid="0"><x id="5"/></mrk><mrk mtype="seg" mid="1">Real sentence.</mrk></seg-source>
<target><mrk mtype="seg" mid="0"><x id="5"/></mrk><mrk mtype="seg" mid="1">Stary przekład.</mrk></target>
<sdl:seg-defs><sdl:seg id="0" conf="Translated"/><sdl:seg id="1" conf="Translated"/></sdl:seg-defs>
</trans-unit>""")


def _roundtrip(tmp_path, sdl_text, strip_mid=False):
    """Convert, fill every target with PL-<n>, merge back, return the tree."""
    src = tmp_path / 'in.sdlxliff'
    src.write_text(sdl_text, encoding='utf-8')
    xlf = tmp_path / 'mid.xlf'
    convert_sdlxliff_to_xliff22([src], xlf, verbose=False)

    tree = etree.parse(str(xlf))
    for n, segment in enumerate(tree.getroot().iter(f'{{{NS22}}}segment'), start=1):
        if strip_mid:
            segment.attrib.pop('sdl-mid', None)
        target = segment.find(f'{{{NS22}}}target')
        if target is None:
            target = etree.SubElement(segment, f'{{{NS22}}}target')
        target.text = f'PL-{n}'
        segment.set('state', 'translated')

    file_elem = tree.getroot().find(f'{{{NS22}}}file')
    out = tmp_path / 'out.sdlxliff'
    counts = update_sdlxliff_targets(
        str(src), build_segment_map_from_file_element(file_elem), str(out)
    )
    return etree.parse(str(out)), counts


def _unit(tree, unit_id):
    return tree.getroot().find(f'.//xliff12:trans-unit[@id="{unit_id}"]', NS12_MAP)


def _mrks(unit):
    target = unit.find('xliff12:target', NS12_MAP)
    return target.findall('.//xliff12:mrk[@mtype="seg"]', NS12_MAP)


def test_converter_carries_mid():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / 'in.sdlxliff'
        src.write_text(NOT_PRETRANSLATED, encoding='utf-8')
        xlf = tmp / 'out.xlf'
        convert_sdlxliff_to_xliff22([src], xlf, verbose=False)

        segments = etree.parse(str(xlf)).getroot().findall(f'.//{{{NS22}}}segment')
        assert [s.get('sdl-mid') for s in segments] == ['0', '1', None]
        # No pre-translation means no target elements at all.
        assert all(s.find(f'{{{NS22}}}target') is None for s in segments)


def test_missing_target_gets_full_mrk_skeleton():
    """Every segment must survive; the old code collapsed the unit to one target."""
    with tempfile.TemporaryDirectory() as tmp:
        tree, (updated, skipped) = _roundtrip(Path(tmp), NOT_PRETRANSLATED)

        mrks = _mrks(_unit(tree, 'u1'))
        assert [m.get('mid') for m in mrks] == ['0', '1']
        assert [m.text for m in mrks] == ['PL-1', 'PL-2']
        # Whitespace between segments is preserved.
        assert mrks[0].tail == ' '
        # An unsegmented unit still gets a flat target.
        assert _unit(tree, 'u2').find('xliff12:target', NS12_MAP).text == 'PL-3'
        assert (updated, skipped) == (3, 0)


def test_missing_target_updates_seg_def_status():
    with tempfile.TemporaryDirectory() as tmp:
        tree, _ = _roundtrip(Path(tmp), NOT_PRETRANSLATED)
        seg_defs = _unit(tree, 'u1').find('sdl:seg-defs', NS12_MAP)
        assert [s.get('conf') for s in seg_defs] == ['Translated', 'Translated']


def test_dropped_tag_only_segment_does_not_shift_translations():
    with tempfile.TemporaryDirectory() as tmp:
        tree, (updated, skipped) = _roundtrip(Path(tmp), TAG_ONLY_SEGMENT)

        mrks = _mrks(_unit(tree, 'b'))
        # mid 0 keeps its placeholder untouched, mid 1 receives the translation.
        assert mrks[0].get('mid') == '0'
        assert mrks[0].text is None
        assert [etree.QName(c).localname for c in mrks[0]] == ['x']
        assert mrks[1].get('mid') == '1' and mrks[1].text == 'PL-1'
        assert (updated, skipped) == (1, 1)


def test_legacy_xliff_without_mid_falls_back_to_position():
    with tempfile.TemporaryDirectory() as tmp:
        tree, (updated, skipped) = _roundtrip(Path(tmp), NOT_PRETRANSLATED, strip_mid=True)
        assert [m.text for m in _mrks(_unit(tree, 'u1'))] == ['PL-1', 'PL-2']
        assert (updated, skipped) == (3, 0)


def test_skeleton_leaves_matching_target_untouched():
    """A properly pre-translated unit must not be rebuilt."""
    tree = etree.fromstring(TAG_ONLY_SEGMENT.encode('utf-8'))
    unit = tree.find('.//xliff12:trans-unit[@id="b"]', NS12_MAP)
    target = unit.find('xliff12:target', NS12_MAP)
    seg_source = unit.find('xliff12:seg-source', NS12_MAP)
    before = target.findall('.//xliff12:mrk[@mtype="seg"]', NS12_MAP)

    mapping = build_target_mrk_skeleton(target, seg_source)

    assert sorted(mapping) == ['0', '1']
    # Same elements, not rebuilt copies, and the existing translation survives.
    assert mapping['0'] is before[0] and mapping['1'] is before[1]
    assert mapping['1'].text == 'Stary przekład.'


def test_unsegmented_unit_returns_empty_mapping():
    tree = etree.fromstring(NOT_PRETRANSLATED.encode('utf-8'))
    unit = tree.find('.//xliff12:trans-unit[@id="u2"]', NS12_MAP)
    target = etree.SubElement(unit, f'{{{NS12}}}target')
    assert build_target_mrk_skeleton(target, None) == {}


def test_loader_reads_every_segment_of_a_unit():
    """A multi-segment unit must produce one grid row per segment."""
    from Xedaibt import XLIFFLoadThread, parse_tags_from_element

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / 'in.sdlxliff'
        src.write_text(NOT_PRETRANSLATED, encoding='utf-8')
        xlf = tmp / 'out.xlf'
        convert_sdlxliff_to_xliff22([src], xlf, verbose=False)

        collected = []
        worker = XLIFFLoadThread(str(xlf), parse_tags_from_element)
        worker.finished.connect(lambda soup, segments, path: collected.append(segments))
        worker.run()

        segments = collected[0]
        assert [s['source'] for s in segments] == [
            '<1>Hello world.</1>', 'Second sentence.', 'Unsegmented unit.'
        ]
        assert all(s['target'] == '' for s in segments)
        assert all(s['state'] == 'initial' for s in segments)
        # Each row must point at its own segment node, not a shared one.
        assert len({id(s['segment_node']) for s in segments}) == 3
