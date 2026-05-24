# Excel Bilingual Filter — Design Spec

Date: 2026-05-24

## Overview

Add a bilingual Excel import/export filter to XLIFF2Editor. The user selects source and target columns, a starting row, and optionally enables SRX-based sentence segmentation. The result is a standard XLIFF 2.2 file with row-origin metadata that allows the merger to write translations back into the original Excel file in-place.

## New files

| File | Purpose |
|---|---|
| `excel_xliff22_converter.py` | Import: Excel → XLIFF 2.2 |
| `xliff22_to_excel_merger.py` | Export: XLIFF 2.2 → Excel in-place |
| `srx_segmenter.py` | SRX parser and sentence splitter (reusable) |
| `segment.srx` | Copied from `~/lfp_aligner/segment.srx` |

Modified file: `Xedaibt.py` — new "Excel" submenu and two handler methods.

New dependency: `openpyxl` (read/write `.xlsx`).

## Import dialog

Class `ExcelImportDialog(QDialog)` defined in `excel_xliff22_converter.py`.

| Field | Widget | Default |
|---|---|---|
| Source language | QLineEdit | `en-US` |
| Target language | QLineEdit | `pl-PL` |
| Source column | QLineEdit | `A` |
| Target column | QLineEdit | `B` |
| First data row | QSpinBox (min 1) | `2` |
| Segment source | QCheckBox | unchecked |

Column fields accept Excel-style letters (A, B, … AA, AB, …). Validation: non-empty, letters only, converted to uppercase.

## Import data flow (`excel_xliff22_converter.py`)

Function signature:
```python
def convert_excel_to_xliff22(
    input_path: str | Path,
    output_path: str | Path,
    src_lang: str,
    tgt_lang: str,
    src_col: str,       # e.g. "A"
    tgt_col: str,       # e.g. "B"
    first_row: int,     # 1-based
    segment: bool,
    srx_path: str | Path | None = None,
) -> dict:             # {"total_units": int, "total_rows": int}
```

Steps:
1. Open the workbook with `openpyxl` (read-only).
2. Iterate rows from `first_row` downward; skip rows where the source cell is empty or whitespace-only.
3. Per non-empty source cell:
   - If `segment=False`: one `<unit>` containing the full cell text.
   - If `segment=True`: run `SrxSegmenter.segment(text, src_lang)` → one `<unit>` per sentence. If the segmenter returns a single sentence (no split), produce one unit.
4. Each `<unit>` carries `x-excel-row="N"` (1-based Excel row number).
5. The `<file>` element carries:
   - `id` = basename of the Excel file
   - `original` = basename of the Excel file (for the merger's dialog default)
   - `x-excel-src-col` = source column letter
   - `x-excel-tgt-col` = target column letter
6. All `<target>` elements are written as empty (`<target/>`).
7. Output uses the standard XLIFF 2.2 namespace (`urn:oasis:names:tc:xliff:document:2.0`), `srcLang` and `trgLang` on the root `<xliff>` element.

Return dict: `{"total_units": N, "total_rows": R}` (units = XLIFF units created; rows = non-empty source rows processed).

## XLIFF 2.2 structure example

Segmentation OFF, two rows:
```xml
<xliff xmlns="urn:oasis:names:tc:xliff:document:2.0"
       version="2.0" srcLang="en-US" trgLang="pl-PL">
  <file id="workbook.xlsx" original="workbook.xlsx"
        x-excel-src-col="A" x-excel-tgt-col="B">
    <unit id="1" x-excel-row="2">
      <segment id="1">
        <source>Hello world.</source>
        <target/>
      </segment>
    </unit>
    <unit id="2" x-excel-row="3">
      <segment id="2">
        <source>How are you?</source>
        <target/>
      </segment>
    </unit>
  </file>
</xliff>
```

Segmentation ON, one row split into two sentences:
```xml
<unit id="1" x-excel-row="2">
  <segment id="1"><source>Hello world.</source><target/></segment>
</unit>
<unit id="2" x-excel-row="2">
  <segment id="2"><source>How are you?</source><target/></segment>
</unit>
```

## SRX segmenter (`srx_segmenter.py`)

Class `SrxSegmenter`:
- `__init__(srx_path)`: parse `segment.srx` with `lxml.etree`; compile all break/non-break regex pairs for every `<languageRule>`.
- `segment(text: str, lang: str) -> list[str]`: find the `<languageRule>` whose `languagePattern` (a regex) matches `lang` (case-insensitive); scan `text` left-to-right; at each position matching a break rule, check all non-break rules — if any match, skip; otherwise split. Strip and drop empty segments. Return `[text]` unchanged if no rules match for the language or no splits found.
- Instantiated once per conversion run (parsing is expensive).
- `srx_path` defaults to `Path(__file__).parent / "segment.srx"` when `None`.

## Export / merger (`xliff22_to_excel_merger.py`)

Function signature:
```python
def merge_xliff22_to_excel(
    xliff_path: str | Path,
    excel_path: str | Path,
) -> dict:    # {"rows_written": int, "units_skipped": int}
```

Steps:
1. Parse the XLIFF with `lxml.etree`; read `x-excel-tgt-col` from the `<file>` element. If attribute is absent, raise `ValueError` (not an Excel-derived XLIFF).
2. Group all `<unit>` elements by `x-excel-row` value (preserving document order within each group).
3. Open the workbook with `openpyxl` (read/write).
4. For each row group: collect `<target>` text from each unit in order; join non-empty texts with a single space. If the joined result is empty, skip (leave cell untouched). Otherwise write to the target column cell.
5. Save workbook to `excel_path` (same file = in-place).
6. Return `{"rows_written": N, "units_skipped": M}`.

## Xedaibt.py changes

New "Excel" submenu under File menu (after the memoQ submenu):
```
File → Excel
         Import from Excel…
         Export to Excel…
```

`import_from_excel()`:
1. Show `ExcelImportDialog`; on cancel return.
2. `QFileDialog.getOpenFileName` for `.xlsx`.
3. `QFileDialog.getSaveFileName` for output `.xlf`/`.xliff`.
4. Call `convert_excel_to_xliff22(...)` in the main thread (Excel files are small; no progress thread needed).
5. Ask "Open converted file?" — same pattern as the SDL/memoQ importers.

`export_to_excel()`:
1. Guard: require an open XLIFF with `x-excel-tgt-col` on its `<file>` element; show warning if absent.
2. Save current XLIFF if modified (same pattern as memoQ exporter).
3. `QFileDialog.getOpenFileName` for the target `.xlsx`; default filename from `original` attribute.
4. Call `merge_xliff22_to_excel(...)`.
5. Show result: "Written N rows."

## Error handling

| Situation | Response |
|---|---|
| `openpyxl` not installed | `QMessageBox.critical` with install hint; method returns |
| Invalid column letter in dialog | Dialog shows inline label "Invalid column"; OK button disabled |
| XLIFF has no `x-excel-*` attributes | `QMessageBox.warning` "This file was not imported from Excel." |
| Row in XLIFF references a row beyond the Excel sheet | Skip silently; include in `units_skipped` count |
| Excel file not writable | Exception propagates to `export_to_excel()`; shown in `QMessageBox.critical` |

## Out of scope

- `.xls` (legacy format) — `openpyxl` supports `.xlsx` only
- Multi-sheet workbooks — first sheet only
- Inline formatting (bold, italic) in cells — plain text only
- Header row preservation — the merger writes only to data rows; header is untouched
