import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import pytest
from lxml import etree

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'
_TEMP_FILES: list = []


def teardown_module(_module):
    import os
    for p in _TEMP_FILES:
        try:
            os.unlink(p)
        except OSError:
            pass


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_srt(lines: list[str]) -> Path:
    """Write a SRT-tab file; lines is a list of 'timecode\\ttext' strings."""
    tmp = tempfile.NamedTemporaryFile(suffix='.srt', delete=False, mode='w', encoding='utf-8')
    tmp.write('\n'.join(lines) + '\n')
    tmp.close()
    _TEMP_FILES.append(tmp.name)
    return Path(tmp.name)


def _out_xliff() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix='.xliff', delete=False)
    tmp.close()
    _TEMP_FILES.append(tmp.name)
    return Path(tmp.name)


def _out_srt() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix='.srt', delete=False)
    tmp.close()
    _TEMP_FILES.append(tmp.name)
    return Path(tmp.name)


def _make_xliff(units) -> Path:
    """units = [(timecode, src_text, tgt_text), ...]. Returns path to temp xliff."""
    root = etree.Element(f'{{{NS22}}}xliff', nsmap={None: NS22})
    root.set('version', '2.2')
    root.set('srcLang', 'en-US')
    root.set('trgLang', 'pl-PL')
    file_elem = etree.SubElement(root, f'{{{NS22}}}file')
    file_elem.set('id', 'test.srt')
    file_elem.set('original', 'test.srt')
    for i, (timecode, src, tgt) in enumerate(units, 1):
        unit = etree.SubElement(file_elem, f'{{{NS22}}}unit')
        unit.set('id', str(i))
        unit.set('x-srt-timecode', timecode)
        unit.set('x-srt-line', str(i))
        seg = etree.SubElement(unit, f'{{{NS22}}}segment')
        seg.set('id', str(i))
        src_e = etree.SubElement(seg, f'{{{NS22}}}source')
        src_e.text = src
        tgt_e = etree.SubElement(seg, f'{{{NS22}}}target')
        tgt_e.text = tgt if tgt else None
    tree = etree.ElementTree(root)
    tmp = tempfile.NamedTemporaryFile(suffix='.xliff', delete=False)
    tree.write(tmp.name, xml_declaration=True, encoding='UTF-8', pretty_print=True)
    tmp.close()
    _TEMP_FILES.append(tmp.name)
    return Path(tmp.name)


# ── srt_xliff22_converter tests ───────────────────────────────────────────────

from srt_xliff22_converter import convert_srt_to_xliff22


def test_converter_basic():
    srt = _make_srt([
        '00:00:01,000 --> 00:00:03,000\tHello world.',
        '00:00:04,000 --> 00:00:06,000\tHow are you?',
    ])
    out = _out_xliff()
    result = convert_srt_to_xliff22(srt, out, 'en-US', 'pl-PL')
    assert result['total_units'] == 2
    assert result['total_lines'] == 2

    tree = etree.parse(str(out))
    root = tree.getroot()
    assert root.get('srcLang') == 'en-US'
    assert root.get('trgLang') == 'pl-PL'

    units = root.findall(f'.//{{{NS22}}}unit')
    assert len(units) == 2
    assert units[0].get('x-srt-timecode') == '00:00:01,000 --> 00:00:03,000'
    assert units[1].get('x-srt-timecode') == '00:00:04,000 --> 00:00:06,000'

    sources = root.findall(f'.//{{{NS22}}}source')
    assert sources[0].text == 'Hello world.'
    assert sources[1].text == 'How are you?'

    targets = root.findall(f'.//{{{NS22}}}target')
    assert all(t.text is None for t in targets)


def test_converter_skips_empty_lines():
    srt = _make_srt([
        '00:00:01,000 --> 00:00:03,000\tFirst.',
        '',
        '00:00:04,000 --> 00:00:06,000\tSecond.',
    ])
    out = _out_xliff()
    result = convert_srt_to_xliff22(srt, out, 'en-US', 'pl-PL')
    assert result['total_units'] == 2


def test_converter_skips_lines_without_tab():
    srt = _make_srt([
        'This line has no tab and should be skipped',
        '00:00:01,000 --> 00:00:03,000\tValid line.',
    ])
    out = _out_xliff()
    result = convert_srt_to_xliff22(srt, out, 'en-US', 'pl-PL')
    assert result['total_units'] == 1
    tree = etree.parse(str(out))
    sources = tree.getroot().findall(f'.//{{{NS22}}}source')
    assert sources[0].text == 'Valid line.'


def test_converter_srt_line_attribute():
    srt = _make_srt([
        '00:00:01,000 --> 00:00:03,000\tFirst.',
        '00:00:04,000 --> 00:00:06,000\tSecond.',
        '00:00:07,000 --> 00:00:09,000\tThird.',
    ])
    out = _out_xliff()
    convert_srt_to_xliff22(srt, out, 'en-US', 'pl-PL')
    tree = etree.parse(str(out))
    units = tree.getroot().findall(f'.//{{{NS22}}}unit')
    assert [u.get('x-srt-line') for u in units] == ['1', '2', '3']


def test_converter_file_metadata():
    srt = _make_srt(['00:00:01,000 --> 00:00:03,000\tHello.'])
    out = _out_xliff()
    convert_srt_to_xliff22(srt, out, 'en-GB', 'de-DE')
    tree = etree.parse(str(out))
    root = tree.getroot()
    assert root.get('srcLang') == 'en-GB'
    assert root.get('trgLang') == 'de-DE'
    file_elem = root.find(f'{{{NS22}}}file')
    assert file_elem.get('original') == Path(srt).name


def test_converter_unit_ids_are_sequential():
    srt = _make_srt([
        '00:00:01,000 --> 00:00:02,000\tA.',
        '00:00:03,000 --> 00:00:04,000\tB.',
        '00:00:05,000 --> 00:00:06,000\tC.',
    ])
    out = _out_xliff()
    convert_srt_to_xliff22(srt, out, 'en-US', 'pl-PL')
    tree = etree.parse(str(out))
    units = tree.getroot().findall(f'.//{{{NS22}}}unit')
    assert [u.get('id') for u in units] == ['1', '2', '3']


# ── xliff22_to_srt_merger tests ───────────────────────────────────────────────

from xliff22_to_srt_merger import merge_xliff22_to_srt


def test_merger_basic():
    xliff = _make_xliff([
        ('00:00:01,000 --> 00:00:03,000', 'Hello world.', 'Witaj świecie.'),
        ('00:00:04,000 --> 00:00:06,000', 'How are you?', 'Jak się masz?'),
    ])
    out = _out_srt()
    result = merge_xliff22_to_srt(xliff, out)
    assert result['lines_written'] == 2

    lines = out.read_text(encoding='utf-8').splitlines()
    assert lines[0] == '00:00:01,000 --> 00:00:03,000\tWitaj świecie.'
    assert lines[1] == '00:00:04,000 --> 00:00:06,000\tJak się masz?'


def test_merger_empty_target_falls_back_to_source():
    xliff = _make_xliff([
        ('00:00:01,000 --> 00:00:03,000', 'Hello world.', ''),
    ])
    out = _out_srt()
    result = merge_xliff22_to_srt(xliff, out)
    assert result['lines_written'] == 1
    lines = out.read_text(encoding='utf-8').splitlines()
    assert lines[0] == '00:00:01,000 --> 00:00:03,000\tHello world.'


def test_merger_preserves_order():
    xliff = _make_xliff([
        ('00:00:01,000 --> 00:00:03,000', 'First.', 'Pierwszy.'),
        ('00:00:04,000 --> 00:00:06,000', 'Second.', 'Drugi.'),
        ('00:00:07,000 --> 00:00:09,000', 'Third.', 'Trzeci.'),
    ])
    out = _out_srt()
    merge_xliff22_to_srt(xliff, out)
    lines = out.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 3
    assert 'Pierwszy.' in lines[0]
    assert 'Drugi.'    in lines[1]
    assert 'Trzeci.'   in lines[2]


def test_merger_raises_on_missing_timecode():
    root = etree.Element(f'{{{NS22}}}xliff', nsmap={None: NS22})
    file_elem = etree.SubElement(root, f'{{{NS22}}}file')
    file_elem.set('id', 'test.srt')
    unit = etree.SubElement(file_elem, f'{{{NS22}}}unit')
    unit.set('id', '1')
    # deliberately omit x-srt-timecode
    tmp = tempfile.NamedTemporaryFile(suffix='.xliff', delete=False)
    etree.ElementTree(root).write(tmp.name, xml_declaration=True, encoding='UTF-8')
    tmp.close()
    _TEMP_FILES.append(tmp.name)
    out = _out_srt()
    with pytest.raises(ValueError, match='x-srt-timecode'):
        merge_xliff22_to_srt(tmp.name, out)


def test_merger_output_ends_with_newline():
    xliff = _make_xliff([
        ('00:00:01,000 --> 00:00:03,000', 'A.', 'B.'),
    ])
    out = _out_srt()
    merge_xliff22_to_srt(xliff, out)
    raw = out.read_bytes()
    assert raw.endswith(b'\n')


# ── round-trip test ───────────────────────────────────────────────────────────

def test_round_trip():
    """Import SRT-tab → edit targets in XLIFF → export back."""
    original_lines = [
        '00:00:01,000 --> 00:00:03,000\tHello.',
        '00:00:04,000 --> 00:00:06,000\tGoodbye.',
    ]
    srt_in = _make_srt(original_lines)
    xliff  = _out_xliff()
    srt_out = _out_srt()

    convert_srt_to_xliff22(srt_in, xliff, 'en-US', 'pl-PL')

    # Simulate translator editing targets.
    tree = etree.parse(str(xliff))
    targets = tree.getroot().findall(f'.//{{{NS22}}}target')
    targets[0].text = 'Cześć.'
    targets[1].text = 'Do widzenia.'
    tree.write(str(xliff), xml_declaration=True, encoding='UTF-8', pretty_print=True)

    merge_xliff22_to_srt(xliff, srt_out)
    lines = srt_out.read_text(encoding='utf-8').splitlines()
    assert lines[0] == '00:00:01,000 --> 00:00:03,000\tCześć.'
    assert lines[1] == '00:00:04,000 --> 00:00:06,000\tDo widzenia.'
