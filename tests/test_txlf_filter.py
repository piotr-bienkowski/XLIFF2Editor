"""Tests for the TXLF ↔ XLIFF 2.2 filter."""

import os
import sys
import shutil
import tempfile
from pathlib import Path
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from txlf_xliff22_converter import (
    convert_txlf_to_xliff22,
    map_txlf_state,
    extract_content_to_xliff22,
)
from xliff22_to_txlf_merger import (
    batch_merge_xliff22_to_txlf,
    map_xliff22_state_to_txlf,
    _build_source_tag_lookup,
)

NS12 = 'urn:oasis:names:tc:xliff:document:1.2'
NS22 = 'urn:oasis:names:tc:xliff:document:2.0'


MIN_TXLF = f"""<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="{NS12}"
       xmlns:gs4tr="http://www.gs4tr.org/schema/xliff-ext" version="1.2">
  <file source-language="en-GB" target-language="pl-PL" datatype="x-ms-word" original="doc.docx">
    <body>
      <trans-unit id="u1">
        <source>Hello world</source>
        <target state="translated">Witaj świecie</target>
      </trans-unit>
      <trans-unit id="u2">
        <source><bx ctype="bold" id="1" rid="1"/>Bold text<ex id="2" rid="1"/></source>
        <target state="translated"><bx ctype="bold" id="1" rid="1"/>Pogrubiony tekst<ex id="2" rid="1"/></target>
      </trans-unit>
      <trans-unit id="u3">
        <source><bpt ctype="x-fmt" id="1" rid="1">&lt;font size="10"&gt;</bpt>Sized<ept id="2" rid="1">&lt;/font&gt;</ept></source>
        <target state="translated"><bpt ctype="x-fmt" id="1" rid="1">&lt;font size="10"&gt;</bpt>Rozmiar<ept id="2" rid="1">&lt;/font&gt;</ept></target>
      </trans-unit>
      <trans-unit id="u4">
        <source>Text with <ph ctype="x-bookmark" id="1">&lt;bm/&gt;</ph>bookmark.</source>
      </trans-unit>
    </body>
  </file>
</xliff>
"""


def _write_min_txlf(tmpdir):
    p = os.path.join(tmpdir, 'sample.txlf')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(MIN_TXLF)
    return p


def test_state_mapping_import():
    assert map_txlf_state('translated') == 'translated'
    assert map_txlf_state('signed-off') == 'final'
    assert map_txlf_state('needs-translation') == 'initial'
    assert map_txlf_state('') == 'initial'
    assert map_txlf_state(None) == 'initial'


def test_state_mapping_export():
    assert map_xliff22_state_to_txlf('initial') == 'needs-translation'
    assert map_xliff22_state_to_txlf('translated') == 'translated'
    assert map_xliff22_state_to_txlf('final') == 'signed-off'
    assert map_xliff22_state_to_txlf('') == 'translated'


def test_import_basic():
    with tempfile.TemporaryDirectory() as td:
        src = _write_min_txlf(td)
        out = os.path.join(td, 'out.xlf')
        result = convert_txlf_to_xliff22([src], out, verbose=False)
        assert result['total_segments'] == 4  # u1, u2, u3, u4 (u4 has source only, no target)
        assert result['total_files'] == 1

        # Verify structure
        tree = etree.parse(out)
        root = tree.getroot()
        assert root.get('srcLang') == 'en-GB'
        assert root.get('trgLang') == 'pl-PL'
        units = root.findall(f'.//{{{NS22}}}unit')
        assert len(units) == 4


def test_import_bx_ex_becomes_pc():
    with tempfile.TemporaryDirectory() as td:
        src = _write_min_txlf(td)
        out = os.path.join(td, 'out.xlf')
        convert_txlf_to_xliff22([src], out, verbose=False)
        tree = etree.parse(out)
        # find unit u2
        for unit in tree.getroot().findall(f'.//{{{NS22}}}unit'):
            if unit.get('id') == 'u2':
                src_elem = unit.find(f'.//{{{NS22}}}source')
                pcs = src_elem.findall(f'{{{NS22}}}pc')
                assert len(pcs) == 1
                assert pcs[0].get('id') == '1'  # matches bx/ex rid
                assert pcs[0].get('type') == 'bold'
                assert (pcs[0].text or '').strip() == 'Bold text'
                break
        else:
            raise AssertionError("u2 not found")


def test_import_bpt_ept_becomes_pc():
    with tempfile.TemporaryDirectory() as td:
        src = _write_min_txlf(td)
        out = os.path.join(td, 'out.xlf')
        convert_txlf_to_xliff22([src], out, verbose=False)
        tree = etree.parse(out)
        for unit in tree.getroot().findall(f'.//{{{NS22}}}unit'):
            if unit.get('id') == 'u3':
                src_elem = unit.find(f'.//{{{NS22}}}source')
                pcs = src_elem.findall(f'{{{NS22}}}pc')
                assert len(pcs) == 1
                assert pcs[0].get('id') == '1'
                assert pcs[0].get('type') == 'x-fmt'
                break
        else:
            raise AssertionError("u3 not found")


def test_import_ph_becomes_ph_without_content():
    with tempfile.TemporaryDirectory() as td:
        src = _write_min_txlf(td)
        out = os.path.join(td, 'out.xlf')
        convert_txlf_to_xliff22([src], out, verbose=False)
        tree = etree.parse(out)
        for unit in tree.getroot().findall(f'.//{{{NS22}}}unit'):
            if unit.get('id') == 'u4':
                src_elem = unit.find(f'.//{{{NS22}}}source')
                phs = src_elem.findall(f'{{{NS22}}}ph')
                assert len(phs) == 1
                assert phs[0].get('id') == '1'
                assert phs[0].get('type') == 'x-bookmark'
                # ph content is dropped on import; will be reinjected on export
                assert (phs[0].text or '') == ''
                break


def test_source_tag_lookup_indexes_all_kinds():
    txlf = etree.fromstring(MIN_TXLF.encode('utf-8'))
    tu3 = None
    for tu in txlf.findall(f'.//{{{NS12}}}trans-unit'):
        if tu.get('id') == 'u3':
            tu3 = tu; break
    src = tu3.find(f'{{{NS12}}}source')
    lookup = _build_source_tag_lookup(src)
    assert '1' in lookup['bpt']
    assert '1' in lookup['ept']  # ept.rid is '1'
    assert lookup['bpt']['1'].get('ctype') == 'x-fmt'


def test_round_trip_preserves_state_and_tags():
    with tempfile.TemporaryDirectory() as td:
        src = _write_min_txlf(td)
        xlf22 = os.path.join(td, 'converted.xlf')
        convert_txlf_to_xliff22([src], xlf22, verbose=False)

        src_dir = os.path.join(td, 'src')
        os.makedirs(src_dir)
        shutil.copy(src, src_dir)
        out_dir = os.path.join(td, 'out')

        results = batch_merge_xliff22_to_txlf(xlf22, src_dir, out_dir, dry_run=False)
        assert len(results) == 1
        assert results[0]['status'] == 'success'
        assert results[0]['updated'] == 3  # u1, u2, u3 have targets; u4 has no target

        # Verify tags reconstructed
        merged = etree.parse(os.path.join(out_dir, 'sample.txlf')).getroot()
        for tu in merged.findall(f'.//{{{NS12}}}trans-unit'):
            tid = tu.get('id')
            tgt = tu.find(f'{{{NS12}}}target')
            if tid == 'u1':
                assert tgt.get('state') == 'translated'
                assert tgt.text and 'Witaj' in tgt.text
            elif tid == 'u2':
                assert tgt.get('state') == 'translated'
                bx = tgt.find(f'{{{NS12}}}bx')
                ex = tgt.find(f'{{{NS12}}}ex')
                assert bx is not None and bx.get('ctype') == 'bold'
                assert ex is not None and ex.get('rid') == '1'
            elif tid == 'u3':
                assert tgt.get('state') == 'translated'
                bpt = tgt.find(f'{{{NS12}}}bpt')
                ept = tgt.find(f'{{{NS12}}}ept')
                assert bpt is not None
                # bpt content preserved from source
                assert bpt.text and 'font size' in bpt.text
                assert ept is not None and 'font' in (ept.text or '')
