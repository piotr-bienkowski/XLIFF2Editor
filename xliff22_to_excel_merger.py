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
