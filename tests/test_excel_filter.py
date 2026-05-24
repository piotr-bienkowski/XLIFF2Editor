import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import pytest
from openpyxl import Workbook, load_workbook  # noqa: F401  (load_workbook used in Task 4)
from lxml import etree

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'
SRX_PATH = Path(__file__).parent.parent / 'segment.srx'
_TEMP_FILES: list = []


def teardown_module(_module):
    import os
    for p in _TEMP_FILES:
        try:
            os.unlink(p)
        except OSError:
            pass


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_excel(rows, first_row=2):
    """Create temp xlsx; rows is list of source strings starting at first_row."""
    wb = Workbook()
    ws = wb.active
    ws['A1'] = 'Source'
    ws['B1'] = 'Target'
    for i, text in enumerate(rows, start=first_row):
        ws.cell(row=i, column=1, value=text)
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    wb.save(tmp.name)
    tmp.close()
    _TEMP_FILES.append(tmp.name)
    return Path(tmp.name)


def _make_xliff(units, tgt_col='B'):
    """units = [(row, source_text, target_text), ...]. Returns path to temp xliff."""
    root = etree.Element(f'{{{NS22}}}xliff', nsmap={None: NS22})
    root.set('version', '2.0')
    root.set('srcLang', 'en-US')
    root.set('trgLang', 'pl-PL')
    file_elem = etree.SubElement(root, f'{{{NS22}}}file')
    file_elem.set('id', 'test.xlsx')
    file_elem.set('original', 'test.xlsx')
    file_elem.set('x-excel-src-col', 'A')
    file_elem.set('x-excel-tgt-col', tgt_col)
    for i, (row, src, tgt) in enumerate(units, 1):
        unit = etree.SubElement(file_elem, f'{{{NS22}}}unit')
        unit.set('id', str(i))
        unit.set('x-excel-row', str(row))
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


# ── SrxSegmenter tests ───────────────────────────────────────────────────────

from srx_segmenter import SrxSegmenter


def test_segmenter_english_two_sentences():
    s = SrxSegmenter(SRX_PATH)
    result = s.segment("Hello world. How are you?", "en-US")
    assert len(result) == 2
    assert result[0] == "Hello world."
    assert result[1] == "How are you?"


def test_segmenter_three_sentences():
    s = SrxSegmenter(SRX_PATH)
    result = s.segment("First sentence. Second sentence. Third sentence.", "en-US")
    assert len(result) == 3


def test_segmenter_single_sentence_no_split():
    s = SrxSegmenter(SRX_PATH)
    result = s.segment("Hello world", "en-US")
    assert result == ["Hello world"]


def test_segmenter_empty_text():
    s = SrxSegmenter(SRX_PATH)
    assert s.segment("", "en-US") == []


def test_segmenter_whitespace_only():
    s = SrxSegmenter(SRX_PATH)
    result = s.segment("   ", "en-US")
    assert result == ["   "]


def test_segmenter_polish_abbreviation_no_split():
    # "adw." (adwokat) is a Polish abbreviation — should not split
    s = SrxSegmenter(SRX_PATH)
    result = s.segment("Adw. Kowalski złożył wniosek.", "pl-PL")
    assert len(result) == 1


def test_segmenter_returns_list_of_strings():
    s = SrxSegmenter(SRX_PATH)
    result = s.segment("Hello. World.", "en-US")
    assert isinstance(result, list)
    assert all(isinstance(r, str) for r in result)
