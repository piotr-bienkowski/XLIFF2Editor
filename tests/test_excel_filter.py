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


# ── placeholder test ─────────────────────────────────────────────────────────

def test_placeholder():
    assert True  # replaced in later tasks
