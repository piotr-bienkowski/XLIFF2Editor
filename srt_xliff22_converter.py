"""
SRT-tab bilingual → XLIFF 2.2 converter.

Expected input format: one subtitle per line, tab-separated:
    timecode<TAB>source text

The timecode (e.g. "00:00:01,000 --> 00:00:05,000") is stored verbatim in
the x-srt-timecode attribute on each <unit>.  Empty lines and lines without a
tab are skipped.

Standalone converter function + PyQt6 import dialog.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QLineEdit,
)

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'


# ── import dialog ─────────────────────────────────────────────────────────────

class SrtImportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import from SRT-tab")
        layout = QFormLayout(self)

        self.src_lang = QLineEdit('en-US')
        self.tgt_lang = QLineEdit('pl-PL')

        layout.addRow('Source language:', self.src_lang)
        layout.addRow('Target language:', self.tgt_lang)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addRow(self._buttons)

    def values(self) -> dict:
        return {
            'src_lang': self.src_lang.text().strip(),
            'tgt_lang': self.tgt_lang.text().strip(),
        }


# ── converter ─────────────────────────────────────────────────────────────────

def convert_srt_to_xliff22(
    input_path,
    output_path,
    src_lang: str,
    tgt_lang: str,
) -> dict:
    """
    Convert a SRT-tab file to XLIFF 2.2.

    Each non-empty input line must contain exactly one tab character separating
    the timecode from the subtitle text.  Lines without a tab are skipped.

    Args:
        input_path:  Path to the source .srt or .txt file.
        output_path: Path where the XLIFF will be written.
        src_lang:    BCP-47 source language tag (e.g. 'en-US').
        tgt_lang:    BCP-47 target language tag (e.g. 'pl-PL').

    Returns:
        {'total_units': int, 'total_lines': int}
    """
    input_path  = Path(input_path)
    output_path = Path(output_path)

    text = input_path.read_text(encoding='utf-8-sig')
    lines = text.splitlines()

    xliff_root = etree.Element(f'{{{NS22}}}xliff', nsmap={None: NS22})
    xliff_root.set('version', '2.2')
    xliff_root.set('srcLang', src_lang)
    xliff_root.set('trgLang', tgt_lang)

    file_elem = etree.SubElement(xliff_root, f'{{{NS22}}}file')
    file_elem.set('id',       input_path.name)
    file_elem.set('original', input_path.name)

    unit_counter = 0
    total_lines  = 0

    for line in lines:
        if not line.strip():
            continue
        if '\t' not in line:
            continue
        timecode, _, source_text = line.partition('\t')
        timecode    = timecode.strip()
        source_text = source_text.strip()
        if not source_text:
            continue
        total_lines += 1

        unit_counter += 1
        unit_elem = etree.SubElement(file_elem, f'{{{NS22}}}unit')
        unit_elem.set('id',              str(unit_counter))
        unit_elem.set('x-srt-timecode', timecode)
        unit_elem.set('x-srt-line',     str(total_lines))

        seg_elem = etree.SubElement(unit_elem, f'{{{NS22}}}segment')
        seg_elem.set('id', str(unit_counter))
        src_elem = etree.SubElement(seg_elem, f'{{{NS22}}}source')
        src_elem.text = source_text
        etree.SubElement(seg_elem, f'{{{NS22}}}target')

    tree = etree.ElementTree(xliff_root)
    tree.write(
        str(output_path),
        xml_declaration=True,
        encoding='UTF-8',
        pretty_print=True,
    )

    return {'total_units': unit_counter, 'total_lines': total_lines}
