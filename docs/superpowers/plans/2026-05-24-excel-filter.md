# Excel Bilingual Filter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a bilingual Excel → XLIFF 2.2 import/export round-trip to XLIFF2Editor, with optional SRX sentence segmentation and in-place Excel write-back.

**Architecture:** Three new standalone modules (`srx_segmenter.py`, `excel_xliff22_converter.py`, `xliff22_to_excel_merger.py`) follow the existing sdlxliff/memoQ converter pattern. `Xedaibt.py` gets an "Excel" submenu wired to two handler methods. Tests live in `tests/test_excel_filter.py`.

**Tech Stack:** `openpyxl` 3.1 (xlsx I/O), `lxml.etree` (XML), `regex` (Unicode-aware SRX regexes), `PyQt6` (dialog), `pytest`.

---

## File Map

| Action | Path |
|---|---|
| Copy | `~/XLIFF2Editor/segment.srx` (from `~/lfp_aligner/segment.srx`) |
| Create | `~/XLIFF2Editor/srx_segmenter.py` |
| Create | `~/XLIFF2Editor/excel_xliff22_converter.py` |
| Create | `~/XLIFF2Editor/xliff22_to_excel_merger.py` |
| Create | `~/XLIFF2Editor/tests/__init__.py` |
| Create | `~/XLIFF2Editor/tests/test_excel_filter.py` |
| Modify | `~/XLIFF2Editor/Xedaibt.py` (menu ~line 999, two new methods after `export_to_mqxliff`) |

---

### Task 1: Setup — copy SRX, create test scaffold

**Files:**
- Create: `~/XLIFF2Editor/segment.srx`
- Create: `~/XLIFF2Editor/tests/__init__.py`
- Create: `~/XLIFF2Editor/tests/test_excel_filter.py`

- [ ] **Step 1: Copy segment.srx**

```bash
cp ~/lfp_aligner/segment.srx ~/XLIFF2Editor/segment.srx
```

Expected: file exists, `ls -lh ~/XLIFF2Editor/segment.srx` shows ~500 KB.

- [ ] **Step 2: Verify dependencies**

```bash
cd ~/XLIFF2Editor && python -c "import openpyxl; import regex; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Create tests directory and scaffold**

```bash
mkdir -p ~/XLIFF2Editor/tests
touch ~/XLIFF2Editor/tests/__init__.py
```

Create `~/XLIFF2Editor/tests/test_excel_filter.py`:

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
import pytest
from openpyxl import Workbook, load_workbook
from lxml import etree

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'
SRX_PATH = Path(__file__).parent.parent / 'segment.srx'


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
    return Path(tmp.name)


# ── placeholder tests (will fail until modules exist) ─────────────────────

def test_placeholder():
    assert True  # replaced in later tasks
```

- [ ] **Step 4: Run scaffold test to confirm pytest works**

```bash
cd ~/XLIFF2Editor && python -m pytest tests/test_excel_filter.py -v
```

Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
cd ~/XLIFF2Editor
git add segment.srx tests/
git commit -m "feat: add segment.srx and test scaffold for Excel filter"
```

---

### Task 2: SRX Segmenter (`srx_segmenter.py`)

**Files:**
- Create: `~/XLIFF2Editor/srx_segmenter.py`
- Modify: `~/XLIFF2Editor/tests/test_excel_filter.py`

- [ ] **Step 1: Write failing tests**

Replace the `test_placeholder` function in `tests/test_excel_filter.py` and add the segmenter tests block (keep all the helpers above it):

```python
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
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd ~/XLIFF2Editor && python -m pytest tests/test_excel_filter.py -v
```

Expected: `ImportError: No module named 'srx_segmenter'`

- [ ] **Step 3: Create `srx_segmenter.py`**

```python
"""
SRX 2.0 sentence segmenter.

Parses segment.srx once at construction; segment() is fast and thread-safe.
Uses the `regex` module for Unicode property support (\p{Lu} etc.);
falls back to stdlib `re` if not installed (loses Unicode properties).
"""

from __future__ import annotations

from pathlib import Path

try:
    import regex as re_module
except ImportError:
    import re as re_module  # type: ignore[no-redef]

from lxml import etree

SRX_NS = 'http://www.lisa.org/srx20'


def _safe_compile(pattern: str):
    """Compile pattern; return None on error."""
    if not pattern:
        return None
    try:
        return re_module.compile(pattern)
    except Exception:
        return None


def _safe_compile_end(pattern: str):
    """Compile pattern anchored to end of string."""
    if not pattern:
        return None
    try:
        return re_module.compile(f'(?:{pattern})$')
    except Exception:
        return None


class SrxSegmenter:
    """
    Parse an SRX file and segment text into sentences.

    Usage:
        segmenter = SrxSegmenter()          # uses segment.srx next to this file
        sentences = segmenter.segment(text, 'en-US')
    """

    def __init__(self, srx_path=None):
        if srx_path is None:
            srx_path = Path(__file__).parent / 'segment.srx'
        # _rules: rulename → [(is_break, b_re, a_re, b_end_re), ...]
        self._rules: dict[str, list] = {}
        # _maps: [(lang_fullmatch_re, rulename), ...]
        self._maps: list = []
        self._parse(Path(srx_path))

    # ── parsing ──────────────────────────────────────────────────────────────

    def _parse(self, path: Path) -> None:
        tree = etree.parse(str(path))
        root = tree.getroot()
        ns = SRX_NS

        for lr in root.findall(f'.//{{{ns}}}languagerule'):
            name = lr.get('languagerulename', '')
            rules = []
            for rule in lr.findall(f'{{{ns}}}rule'):
                is_break = rule.get('break', 'yes') == 'yes'
                before = rule.findtext(f'{{{ns}}}beforebreak') or ''
                after  = rule.findtext(f'{{{ns}}}afterbreak')  or ''
                b_re     = _safe_compile(before)
                a_re     = _safe_compile(after)
                b_end_re = _safe_compile_end(before)
                if b_re is not None or a_re is not None:
                    rules.append((is_break, b_re, a_re, b_end_re))
            self._rules[name] = rules

        for lm in root.findall(f'.//{{{ns}}}languagemap'):
            pattern  = lm.get('languagepattern', '')
            rulename = lm.get('languagerulename', '')
            try:
                lp_re = re_module.compile(pattern, re_module.IGNORECASE)
                self._maps.append((lp_re, rulename))
            except Exception:
                pass

    # ── public API ───────────────────────────────────────────────────────────

    def segment(self, text: str, lang: str) -> list[str]:
        """
        Split *text* into sentences using the SRX rules for *lang*.

        Returns ``[text]`` unchanged when no split is found.
        Returns ``[]`` when *text* is empty.
        """
        if not text:
            return []
        if not text.strip():
            return [text]

        rules = self._get_rules(lang)
        if not rules:
            return [text]

        break_rules   = [(b_re, a_re)
                         for (ib, b_re, a_re, _bnd) in rules if ib]
        nobreak_rules = [(b_end_re, a_re)
                         for (ib, _b, a_re, b_end_re) in rules if not ib]

        candidates = self._find_candidates(text, break_rules)
        if not candidates:
            return [text]

        real_breaks = self._filter_nobreaks(text, candidates, nobreak_rules)
        if not real_breaks:
            return [text]

        return self._split(text, real_breaks)

    # ── internals ────────────────────────────────────────────────────────────

    def _get_rules(self, lang: str) -> list:
        """Collect rules from all language maps matching *lang* (cascade)."""
        combined: list = []
        for lp_re, rulename in self._maps:
            if lp_re.fullmatch(lang):
                combined.extend(self._rules.get(rulename, []))
        return combined

    def _find_candidates(self, text: str, break_rules: list) -> set[int]:
        """Return set of candidate break positions (end of beforebreak match)."""
        candidates: set[int] = set()
        for b_re, a_re in break_rules:
            if b_re is None:
                continue
            for m in b_re.finditer(text):
                pos = m.end()
                if pos >= len(text):
                    continue
                if a_re is None or not a_re.pattern or a_re.match(text[pos:]):
                    candidates.add(pos)
        return candidates

    def _filter_nobreaks(
        self, text: str, candidates: set[int], nobreak_rules: list
    ) -> set[int]:
        """Remove candidates that are inhibited by a no-break rule."""
        real: set[int] = set()
        for pos in candidates:
            after = text[pos:]
            inhibited = False
            for b_end_re, a_re in nobreak_rules:
                if b_end_re is None:
                    continue
                if not b_end_re.search(text[:pos]):
                    continue
                if a_re is None or not a_re.pattern or a_re.match(after):
                    inhibited = True
                    break
            if not inhibited:
                real.add(pos)
        return real

    def _split(self, text: str, breaks: set[int]) -> list[str]:
        result: list[str] = []
        prev = 0
        for pos in sorted(breaks):
            seg = text[prev:pos].strip()
            if seg:
                result.append(seg)
            prev = pos
        tail = text[prev:].strip()
        if tail:
            result.append(tail)
        return result if result else [text]
```

- [ ] **Step 4: Run tests**

```bash
cd ~/XLIFF2Editor && python -m pytest tests/test_excel_filter.py -v
```

Expected: all 7 segmenter tests pass. If `test_segmenter_polish_abbreviation_no_split` fails, check that the Polish rule `\b[Aa]dw?\.\s` is present in `segment.srx` — it should be. If the two-sentence test fails, inspect what `segment()` returns and adjust the test text (different period-space patterns work differently per language rule set).

- [ ] **Step 5: Commit**

```bash
cd ~/XLIFF2Editor
git add srx_segmenter.py tests/test_excel_filter.py
git commit -m "feat: add SrxSegmenter with SRX 2.0 cascade support"
```

---

### Task 3: Excel → XLIFF 2.2 converter (`excel_xliff22_converter.py`)

**Files:**
- Create: `~/XLIFF2Editor/excel_xliff22_converter.py`
- Modify: `~/XLIFF2Editor/tests/test_excel_filter.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_excel_filter.py` (after the segmenter tests):

```python
# ── excel_xliff22_converter tests ────────────────────────────────────────────

from excel_xliff22_converter import convert_excel_to_xliff22


def _out_xliff():
    tmp = tempfile.NamedTemporaryFile(suffix='.xliff', delete=False)
    tmp.close()
    return Path(tmp.name)


def test_converter_basic():
    excel = _make_excel(['Hello world.', 'How are you?'])
    out = _out_xliff()
    result = convert_excel_to_xliff22(excel, out, 'en-US', 'pl-PL', 'A', 'B', 2, False)
    assert result['total_rows'] == 2
    assert result['total_units'] == 2

    tree = etree.parse(str(out))
    root = tree.getroot()
    units = root.findall(f'.//{{{NS22}}}unit')
    assert len(units) == 2
    assert units[0].get('x-excel-row') == '2'
    assert units[1].get('x-excel-row') == '3'
    sources = root.findall(f'.//{{{NS22}}}source')
    assert sources[0].text == 'Hello world.'
    assert sources[1].text == 'How are you?'
    targets = root.findall(f'.//{{{NS22}}}target')
    assert all(t.text is None for t in targets)


def test_converter_skips_empty_source():
    excel = _make_excel(['Hello.', None, 'World.'])
    out = _out_xliff()
    result = convert_excel_to_xliff22(excel, out, 'en-US', 'pl-PL', 'A', 'B', 2, False)
    assert result['total_rows'] == 2
    assert result['total_units'] == 2


def test_converter_file_metadata():
    excel = _make_excel(['Hello.'])
    out = _out_xliff()
    convert_excel_to_xliff22(excel, out, 'en-US', 'pl-PL', 'A', 'B', 2, False)
    tree = etree.parse(str(out))
    root = tree.getroot()
    assert root.get('srcLang') == 'en-US'
    assert root.get('trgLang') == 'pl-PL'
    file_elem = root.find(f'{{{NS22}}}file')
    assert file_elem.get('x-excel-src-col') == 'A'
    assert file_elem.get('x-excel-tgt-col') == 'B'


def test_converter_segmentation_splits_units():
    excel = _make_excel(['First sentence. Second sentence.'])
    out = _out_xliff()
    result = convert_excel_to_xliff22(
        excel, out, 'en-US', 'pl-PL', 'A', 'B', 2, True,
        srx_path=SRX_PATH
    )
    assert result['total_rows'] == 1
    assert result['total_units'] == 2
    tree = etree.parse(str(out))
    units = tree.getroot().findall(f'.//{{{NS22}}}unit')
    assert len(units) == 2
    # both units refer to the same Excel row
    assert units[0].get('x-excel-row') == '2'
    assert units[1].get('x-excel-row') == '2'


def test_converter_column_b():
    wb = Workbook()
    ws = wb.active
    ws['B2'] = 'Source in B'
    ws['C2'] = None
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    wb.save(tmp.name)
    tmp.close()
    out = _out_xliff()
    result = convert_excel_to_xliff22(tmp.name, out, 'en-US', 'pl-PL', 'B', 'C', 2, False)
    assert result['total_rows'] == 1
    tree = etree.parse(str(out))
    src = tree.getroot().find(f'.//{{{NS22}}}source')
    assert src.text == 'Source in B'
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd ~/XLIFF2Editor && python -m pytest tests/test_excel_filter.py::test_converter_basic -v
```

Expected: `ImportError: No module named 'excel_xliff22_converter'`

- [ ] **Step 3: Create `excel_xliff22_converter.py`**

```python
"""
Excel bilingual → XLIFF 2.2 converter.

Standalone converter function + PyQt6 import dialog.
"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QCheckBox,
)

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'
_COL_RE = re.compile(r'^[A-Za-z]{1,3}$')


# ── import dialog ─────────────────────────────────────────────────────────────

class ExcelImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import from Excel")
        layout = QFormLayout(self)

        self.src_lang  = QLineEdit('en-US')
        self.tgt_lang  = QLineEdit('pl-PL')
        self.src_col   = QLineEdit('A')
        self.tgt_col   = QLineEdit('B')
        self.first_row = QSpinBox()
        self.first_row.setMinimum(1)
        self.first_row.setValue(2)
        self.segment_cb = QCheckBox()
        self._col_error = QLabel()
        self._col_error.setStyleSheet('color: red;')

        layout.addRow('Source language:', self.src_lang)
        layout.addRow('Target language:', self.tgt_lang)
        layout.addRow('Source column:',  self.src_col)
        layout.addRow('Target column:',  self.tgt_col)
        layout.addRow('', self._col_error)
        layout.addRow('First data row:', self.first_row)
        layout.addRow('Segment source:', self.segment_cb)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addRow(self._buttons)

        self.src_col.textChanged.connect(self._validate_cols)
        self.tgt_col.textChanged.connect(self._validate_cols)

    def _validate_cols(self) -> None:
        ok = bool(_COL_RE.match(self.src_col.text())) and \
             bool(_COL_RE.match(self.tgt_col.text()))
        self._col_error.setText('' if ok else 'Invalid column (use A–Z or AA–ZZ)')
        self._buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)

    def values(self) -> dict:
        return {
            'src_lang':  self.src_lang.text().strip(),
            'tgt_lang':  self.tgt_lang.text().strip(),
            'src_col':   self.src_col.text().upper().strip(),
            'tgt_col':   self.tgt_col.text().upper().strip(),
            'first_row': self.first_row.value(),
            'segment':   self.segment_cb.isChecked(),
        }


# ── converter ────────────────────────────────────────────────────────────────

def convert_excel_to_xliff22(
    input_path,
    output_path,
    src_lang: str,
    tgt_lang: str,
    src_col: str,
    tgt_col: str,
    first_row: int,
    segment: bool,
    srx_path=None,
) -> dict:
    """
    Convert a bilingual Excel workbook to XLIFF 2.2.

    Args:
        input_path:  Path to the source .xlsx file.
        output_path: Path where the XLIFF will be written.
        src_lang:    BCP-47 source language tag (e.g. 'en-US').
        tgt_lang:    BCP-47 target language tag (e.g. 'pl-PL').
        src_col:     Excel column letter(s) for the source (e.g. 'A').
        tgt_col:     Excel column letter(s) for the target (e.g. 'B').
        first_row:   1-based first data row (rows above are ignored).
        segment:     When True, split source cells into sentence-level units.
        srx_path:    Path to segment.srx; defaults to segment.srx next to this file.

    Returns:
        {'total_units': int, 'total_rows': int}
    """
    input_path  = Path(input_path)
    output_path = Path(output_path)
    src_col_idx = column_index_from_string(src_col.upper())

    segmenter = None
    if segment:
        from srx_segmenter import SrxSegmenter
        segmenter = SrxSegmenter(srx_path)

    wb = load_workbook(str(input_path), read_only=True, data_only=True)
    ws = wb.active
    max_row = ws.max_row or 0

    xliff_root = etree.Element(f'{{{NS22}}}xliff', nsmap={None: NS22})
    xliff_root.set('version', '2.0')
    xliff_root.set('srcLang', src_lang)
    xliff_root.set('trgLang', tgt_lang)

    file_elem = etree.SubElement(xliff_root, f'{{{NS22}}}file')
    file_elem.set('id',              input_path.name)
    file_elem.set('original',        input_path.name)
    file_elem.set('x-excel-src-col', src_col.upper())
    file_elem.set('x-excel-tgt-col', tgt_col.upper())

    unit_counter = 0
    seg_counter  = 0
    total_rows   = 0

    for row_idx in range(first_row, max_row + 1):
        cell  = ws.cell(row=row_idx, column=src_col_idx)
        value = cell.value
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        total_rows += 1

        sentences = segmenter.segment(text, src_lang) if segmenter else [text]

        for sentence in sentences:
            unit_counter += 1
            seg_counter  += 1
            unit_elem = etree.SubElement(file_elem, f'{{{NS22}}}unit')
            unit_elem.set('id',           str(unit_counter))
            unit_elem.set('x-excel-row',  str(row_idx))
            seg_elem = etree.SubElement(unit_elem, f'{{{NS22}}}segment')
            seg_elem.set('id', str(seg_counter))
            src_elem = etree.SubElement(seg_elem, f'{{{NS22}}}source')
            src_elem.text = sentence
            etree.SubElement(seg_elem, f'{{{NS22}}}target')

    wb.close()

    tree = etree.ElementTree(xliff_root)
    tree.write(
        str(output_path),
        xml_declaration=True,
        encoding='UTF-8',
        pretty_print=True,
    )

    return {'total_units': unit_counter, 'total_rows': total_rows}
```

- [ ] **Step 4: Run tests**

```bash
cd ~/XLIFF2Editor && python -m pytest tests/test_excel_filter.py -v -k "converter"
```

Expected: all 5 converter tests pass.

- [ ] **Step 5: Commit**

```bash
cd ~/XLIFF2Editor
git add excel_xliff22_converter.py tests/test_excel_filter.py
git commit -m "feat: add Excel → XLIFF 2.2 converter with import dialog"
```

---

### Task 4: XLIFF 2.2 → Excel merger (`xliff22_to_excel_merger.py`)

**Files:**
- Create: `~/XLIFF2Editor/xliff22_to_excel_merger.py`
- Modify: `~/XLIFF2Editor/tests/test_excel_filter.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_excel_filter.py`:

```python
# ── xliff22_to_excel_merger tests ────────────────────────────────────────────

from xliff22_to_excel_merger import merge_xliff22_to_excel


def _make_excel_for_merge(rows):
    """Create temp xlsx with source rows starting at row 2 (col A only)."""
    wb = Workbook()
    ws = wb.active
    for i, text in enumerate(rows, start=2):
        ws.cell(row=i, column=1, value=text)
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    wb.save(tmp.name)
    tmp.close()
    return Path(tmp.name)


def test_merger_basic():
    xliff = _make_xliff([
        (2, 'Hello world.', 'Witaj świecie.'),
        (3, 'How are you?', 'Jak się masz?'),
    ])
    excel = _make_excel_for_merge(['Hello world.', 'How are you?'])
    result = merge_xliff22_to_excel(xliff, excel)
    assert result['rows_written'] == 2
    wb = load_workbook(str(excel))
    ws = wb.active
    assert ws.cell(row=2, column=2).value == 'Witaj świecie.'
    assert ws.cell(row=3, column=2).value == 'Jak się masz?'


def test_merger_joins_segmented_units():
    xliff = _make_xliff([
        (2, 'First.', 'Pierwszy.'),
        (2, 'Second.', 'Drugi.'),
    ])
    excel = _make_excel_for_merge(['First. Second.'])
    result = merge_xliff22_to_excel(xliff, excel)
    assert result['rows_written'] == 1
    wb = load_workbook(str(excel))
    ws = wb.active
    assert ws.cell(row=2, column=2).value == 'Pierwszy. Drugi.'


def test_merger_skips_empty_targets():
    xliff = _make_xliff([
        (2, 'Hello.', ''),
        (3, 'World.', 'Świat.'),
    ])
    excel = _make_excel_for_merge(['Hello.', 'World.'])
    result = merge_xliff22_to_excel(xliff, excel)
    assert result['rows_written'] == 1
    wb = load_workbook(str(excel))
    ws = wb.active
    assert ws.cell(row=2, column=2).value is None
    assert ws.cell(row=3, column=2).value == 'Świat.'


def test_merger_raises_on_missing_metadata():
    root = etree.Element(f'{{{NS22}}}xliff', nsmap={None: NS22})
    file_elem = etree.SubElement(root, f'{{{NS22}}}file')
    file_elem.set('id', 'test.xlsx')
    tmp = tempfile.NamedTemporaryFile(suffix='.xliff', delete=False)
    etree.ElementTree(root).write(tmp.name)
    tmp.close()
    with pytest.raises(ValueError, match='x-excel-tgt-col'):
        merge_xliff22_to_excel(tmp.name, '/tmp/irrelevant.xlsx')


def test_merger_row_beyond_sheet_skipped():
    xliff = _make_xliff([
        (2, 'Present.', 'Obecny.'),
        (999, 'Beyond.', 'Poza.'),  # row 999, sheet only has row 2
    ])
    excel = _make_excel_for_merge(['Present.'])
    result = merge_xliff22_to_excel(xliff, excel)
    assert result['rows_written'] == 1
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd ~/XLIFF2Editor && python -m pytest tests/test_excel_filter.py::test_merger_basic -v
```

Expected: `ImportError: No module named 'xliff22_to_excel_merger'`

- [ ] **Step 3: Create `xliff22_to_excel_merger.py`**

```python
"""
XLIFF 2.2 → Excel merger.

Reads translations from an XLIFF 2.2 file produced by excel_xliff22_converter
and writes them back to the original Excel workbook in-place (target column).
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from lxml import etree
from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'


def merge_xliff22_to_excel(xliff_path, excel_path) -> dict:
    """
    Write translations from *xliff_path* into the target column of *excel_path*.

    The XLIFF must have been produced by convert_excel_to_xliff22 (requires the
    ``x-excel-tgt-col`` attribute on the ``<file>`` element).

    Multiple units sharing the same ``x-excel-row`` (from segmentation) are
    joined with a single space before writing.

    Args:
        xliff_path:  Path to the translated XLIFF 2.2 file.
        excel_path:  Path to the Excel workbook to update in-place.

    Returns:
        {'rows_written': int, 'units_skipped': int}

    Raises:
        ValueError: if the XLIFF was not created by the Excel converter.
    """
    xliff_path = Path(xliff_path)
    excel_path = Path(excel_path)

    tree = etree.parse(str(xliff_path))
    root = tree.getroot()

    file_elem = root.find(f'{{{NS22}}}file')
    if file_elem is None:
        raise ValueError("No <file> element found in XLIFF.")
    tgt_col = file_elem.get('x-excel-tgt-col')
    if not tgt_col:
        raise ValueError(
            "This file was not imported from Excel (missing x-excel-tgt-col)."
        )
    tgt_col_idx = column_index_from_string(tgt_col)

    # Group translated texts by Excel row (preserve document order)
    row_texts: dict[int, list[str]] = defaultdict(list)
    units_skipped = 0

    for unit in root.findall(f'.//{{{NS22}}}unit'):
        row_str = unit.get('x-excel-row')
        if not row_str:
            units_skipped += 1
            continue
        row = int(row_str)
        for seg in unit.findall(f'{{{NS22}}}segment'):
            tgt = seg.find(f'{{{NS22}}}target')
            if tgt is not None and tgt.text:
                text = tgt.text.strip()
                if text:
                    row_texts[row].append(text)

    wb = load_workbook(str(excel_path))
    ws = wb.active
    max_row = ws.max_row or 0
    rows_written = 0

    for row, texts in row_texts.items():
        joined = ' '.join(texts)
        if not joined:
            units_skipped += 1
            continue
        if row > max_row:
            units_skipped += 1
            continue
        ws.cell(row=row, column=tgt_col_idx).value = joined
        rows_written += 1

    wb.save(str(excel_path))
    return {'rows_written': rows_written, 'units_skipped': units_skipped}
```

- [ ] **Step 4: Run tests**

```bash
cd ~/XLIFF2Editor && python -m pytest tests/test_excel_filter.py -v -k "merger"
```

Expected: all 5 merger tests pass.

- [ ] **Step 5: Run full test suite**

```bash
cd ~/XLIFF2Editor && python -m pytest tests/test_excel_filter.py -v
```

Expected: all tests pass (segmenter + converter + merger).

- [ ] **Step 6: Commit**

```bash
cd ~/XLIFF2Editor
git add xliff22_to_excel_merger.py tests/test_excel_filter.py
git commit -m "feat: add XLIFF 2.2 → Excel merger"
```

---

### Task 5: Xedaibt.py integration

**Files:**
- Modify: `~/XLIFF2Editor/Xedaibt.py`

- [ ] **Step 1: Add Excel submenu to `init_ui()`**

In `Xedaibt.py`, find the block ending at line ~999:

```python
        for name, shortcut, callback in mqxliff_actions:
            act = QAction(name, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(callback)
            mqxliff_menu.addAction(act)

        file_menu.addSeparator()
```

Replace it with:

```python
        for name, shortcut, callback in mqxliff_actions:
            act = QAction(name, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(callback)
            mqxliff_menu.addAction(act)

        # Excel submenu
        excel_menu = file_menu.addMenu("Excel")
        excel_actions = [
            ("Import from Excel...", None, self.import_from_excel),
            ("Export to Excel...",   None, self.export_to_excel),
        ]
        for name, shortcut, callback in excel_actions:
            act = QAction(name, self)
            if shortcut:
                act.setShortcut(QKeySequence(shortcut))
            act.triggered.connect(callback)
            excel_menu.addAction(act)

        file_menu.addSeparator()
```

- [ ] **Step 2: Add `import_from_excel()` method**

In `Xedaibt.py`, find the end of `export_to_mqxliff()` (ends with `f"Failed to merge back to MQXLIFF:\n\n{str(e)}")`). Add the new method immediately after:

```python
    def import_from_excel(self):
        """Import bilingual Excel file and convert to XLIFF 2.2"""
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            QMessageBox.critical(
                self, "Module Missing",
                "openpyxl is not installed.\n\nInstall it with:\n  pip install openpyxl"
            )
            return

        try:
            import excel_xliff22_converter as converter
            from excel_xliff22_converter import ExcelImportDialog
        except ImportError:
            QMessageBox.critical(
                self, "Module Missing",
                "excel_xliff22_converter.py is not found.\n\n"
                "Please ensure it's in the same directory as this editor."
            )
            return

        dialog = ExcelImportDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        params = dialog.values()

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Excel File", "",
            "Excel Files (*.xlsx);;All Files (*)"
        )
        if not file_path:
            return

        output_path, _ = QFileDialog.getSaveFileName(
            self, "Save Converted XLIFF 2.2 File", "",
            "XLIFF Files (*.xlf *.xliff);;All Files (*)"
        )
        if not output_path:
            return

        try:
            result = converter.convert_excel_to_xliff22(
                input_path=file_path,
                output_path=output_path,
                src_lang=params['src_lang'],
                tgt_lang=params['tgt_lang'],
                src_col=params['src_col'],
                tgt_col=params['tgt_col'],
                first_row=params['first_row'],
                segment=params['segment'],
            )
            reply = QMessageBox.question(
                self, "Conversion Successful",
                f"Converted {result['total_rows']} row(s) into "
                f"{result['total_units']} unit(s).\n\nOpen the converted file now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.open_xliff_file(str(output_path))
        except Exception as e:
            QMessageBox.critical(self, "Conversion Error",
                                 f"Failed to convert Excel file:\n\n{str(e)}")

    def export_to_excel(self):
        """Export current XLIFF 2.2 translations back to Excel in-place"""
        if not self.xliff_soup:
            QMessageBox.warning(self, "No File Open",
                                "Please open an XLIFF 2.2 file first.")
            return

        file_tag = self.xliff_soup.find('file')
        if not file_tag or not file_tag.get('x-excel-tgt-col'):
            QMessageBox.warning(
                self, "Not an Excel XLIFF",
                "This file was not imported from Excel.\n\n"
                "Only XLIFF files created via Excel import can be exported back."
            )
            return

        try:
            import openpyxl  # noqa: F401
        except ImportError:
            QMessageBox.critical(
                self, "Module Missing",
                "openpyxl is not installed.\n\nInstall it with:\n  pip install openpyxl"
            )
            return

        try:
            import xliff22_to_excel_merger as merger
        except ImportError:
            QMessageBox.critical(
                self, "Module Missing",
                "xliff22_to_excel_merger.py is not found.\n\n"
                "Please ensure it's in the same directory as this editor."
            )
            return

        if self.is_modified:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "Save changes to XLIFF 2.2 file before exporting?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            elif reply == QMessageBox.StandardButton.Yes:
                self.save_xliff()

        default_name = file_tag.get('original', '')
        excel_path, _ = QFileDialog.getOpenFileName(
            self, "Select Target Excel File", default_name,
            "Excel Files (*.xlsx);;All Files (*)"
        )
        if not excel_path:
            return

        try:
            result = merger.merge_xliff22_to_excel(self.filepath, excel_path)
            QMessageBox.information(
                self, "Export Successful",
                f"Written {result['rows_written']} row(s) to "
                f"{Path(excel_path).name}."
            )
        except ValueError as e:
            QMessageBox.warning(self, "Export Error", str(e))
        except Exception as e:
            QMessageBox.critical(self, "Export Error",
                                 f"Failed to write to Excel file:\n\n{str(e)}")
```

- [ ] **Step 3: Run full test suite to confirm nothing broken**

```bash
cd ~/XLIFF2Editor && python -m pytest tests/test_excel_filter.py -v
```

Expected: all tests pass.

- [ ] **Step 4: Smoke-test the UI**

```bash
cd ~ && python -m XLIFF2Editor
```

Verify:
1. File menu shows "Excel" submenu between "memoQ" and the Save separator
2. "Import from Excel…" opens the dialog with all 6 fields
3. Dialog OK button disables when column is cleared; re-enables with "A"
4. Cancel closes without action

- [ ] **Step 5: Commit**

```bash
cd ~/XLIFF2Editor
git add Xedaibt.py
git commit -m "feat: wire Excel import/export into XLIFF2Editor menu"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| Dialog: src/tgt lang, columns, first row, segment checkbox | Task 3 (ExcelImportDialog) |
| Skip empty source cells | Task 3 (converter loop) |
| `x-excel-row` metadata on each unit | Task 3 (converter) |
| `x-excel-src-col` / `x-excel-tgt-col` on `<file>` | Task 3 (converter) |
| SRX segmentation → N units per cell, same row | Task 2 (segmenter) + Task 3 |
| Excel import menu item | Task 5 |
| Excel export menu item | Task 5 |
| Export in-place, fills target column | Task 4 (merger) |
| Join segmented units by row on export | Task 4 (merger) |
| Skip empty targets on export | Task 4 (merger) |
| openpyxl missing → clear error | Task 5 (both handlers) |
| Invalid column → dialog error label | Task 3 (ExcelImportDialog._validate_cols) |
| XLIFF missing x-excel-* → warning | Task 5 (export_to_excel guard) + Task 4 (ValueError) |
| Row beyond sheet → skip silently | Task 4 (merger) |
| segment.srx copied from lfp_aligner | Task 1 |

All requirements covered. No gaps found.
