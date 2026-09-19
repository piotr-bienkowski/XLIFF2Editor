"""
XLIFF 2.2 → SRT-tab merger.

Reads translations from an XLIFF 2.2 file produced by srt_xliff22_converter
and writes them back as a tab-separated SRT-tab file:

    timecode<TAB>translated text

Units are written in document order (by x-srt-line).  Units whose target is
empty are written with the source text as a fallback so the timecode is
preserved and the line count stays intact.
"""

from __future__ import annotations

from pathlib import Path

from lxml import etree

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'


def _collect_text(elem) -> str:
    """Concatenate text content of an element, ignoring inline tags."""
    if elem is None:
        return ''
    parts = [elem.text or '']
    for child in elem:
        parts.append(child.get('equiv', '') or (child.text or ''))
        parts.append(child.tail or '')
    return ''.join(parts).strip()


def merge_xliff22_to_srt(xliff_path, output_path) -> dict:
    """
    Write translations from *xliff_path* to *output_path* in SRT-tab format.

    The XLIFF must have been produced by convert_srt_to_xliff22 (requires the
    ``x-srt-timecode`` attribute on every ``<unit>`` element).

    Args:
        xliff_path:  Path to the translated XLIFF 2.2 file.
        output_path: Path where the SRT-tab output will be written.

    Returns:
        {'lines_written': int, 'units_skipped': int}

    Raises:
        ValueError: if the XLIFF was not created by the SRT converter.
    """
    xliff_path  = Path(xliff_path)
    output_path = Path(output_path)

    tree = etree.parse(str(xliff_path))
    root = tree.getroot()

    file_elem = root.find(f'{{{NS22}}}file')
    if file_elem is None:
        raise ValueError("No <file> element found in XLIFF.")

    units = root.findall(f'.//{{{NS22}}}unit')
    if units and all(u.get('x-srt-timecode') is None for u in units):
        raise ValueError(
            "This file was not imported from SRT-tab (missing x-srt-timecode)."
        )

    # Sort by x-srt-line to guarantee document order.
    def _sort_key(u):
        v = u.get('x-srt-line', '0')
        try:
            return int(v)
        except ValueError:
            return 0

    units_sorted = sorted(units, key=_sort_key)

    lines_written  = 0
    units_skipped  = 0
    output_lines: list[str] = []

    for unit in units_sorted:
        timecode = unit.get('x-srt-timecode')
        if timecode is None:
            units_skipped += 1
            continue

        seg = unit.find(f'{{{NS22}}}segment')
        if seg is None:
            units_skipped += 1
            continue

        tgt  = seg.find(f'{{{NS22}}}target')
        src  = seg.find(f'{{{NS22}}}source')
        text = _collect_text(tgt)
        if not text:
            text = _collect_text(src)  # fallback: keep source so line survives
        if not text:
            units_skipped += 1
            continue

        output_lines.append(f"{timecode}\t{text}")
        lines_written += 1

    output_path.write_text('\n'.join(output_lines) + '\n', encoding='utf-8')
    return {'lines_written': lines_written, 'units_skipped': units_skipped}
