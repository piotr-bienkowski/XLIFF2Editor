"""Ctrl+E confirms and advances; Ctrl+> / Ctrl+< just move."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from PyQt6.QtWidgets import QApplication

from Xedaibt import XLIFFEditor

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'

XLIFF = f"""<?xml version="1.0" encoding="UTF-8"?>
<xliff xmlns="{NS22}" version="2.2" srcLang="de-DE" trgLang="pl-PL">
<file id="f1">
<unit id="u1"><segment id="1"><source>Eins.</source></segment></unit>
<unit id="u2"><segment id="2"><source>Zwei.</source></segment></unit>
<unit id="u3"><segment id="3"><source>Drei.</source></segment></unit>
</file></xliff>"""


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def editor(app, tmp_path):
    path = tmp_path / 'nav.xlf'
    path.write_text(XLIFF, encoding='utf-8')
    window = XLIFFEditor()
    window.open_xliff_file(str(path))
    window.xliff_thread.wait()
    app.processEvents()
    window.table.setCurrentCell(0, 3)
    app.processEvents()
    yield window
    window.close()


def test_confirming_advances_to_the_next_segment(editor):
    editor.set_current_translated()

    assert editor.segments[0]['state'] == 'translated'
    assert editor.table.item(0, 4).text() == 'translated'
    assert editor.current_row == 1
    assert editor.table.currentColumn() == 3      # the target cell, ready to type


def test_confirming_the_last_segment_stays_put(editor):
    editor.table.setCurrentCell(2, 3)
    assert editor.set_current_translated() is None
    assert editor.segments[2]['state'] == 'translated'
    assert editor.current_row == 2


def test_navigation_does_not_change_status(editor):
    assert editor.goto_next_segment() is True
    assert editor.current_row == 1
    assert editor.segments[0]['state'] == 'initial'
    assert editor.segments[1]['state'] == 'initial'

    assert editor.goto_previous_segment() is True
    assert editor.current_row == 0
    assert all(seg['state'] == 'initial' for seg in editor.segments)


def test_navigation_stops_at_the_ends(editor):
    assert editor.goto_previous_segment() is False
    assert editor.current_row == 0

    editor.table.setCurrentCell(2, 3)
    assert editor.goto_next_segment() is False
    assert editor.current_row == 2


def test_filtered_out_rows_are_skipped(editor):
    editor.table.setRowHidden(1, True)

    assert editor.goto_next_segment() is True
    assert editor.current_row == 2

    assert editor.goto_previous_segment() is True
    assert editor.current_row == 0


def test_shortcuts_are_registered(editor):
    shortcuts = {
        action.text(): [key.toString() for key in action.shortcuts()]
        for action in editor.findChildren(type(editor.menuBar().actions()[0]))
    }
    assert shortcuts['Set Status to Translated'] == ['Ctrl+E']
    assert shortcuts['Next Segment'] == ['Ctrl+.']
    assert shortcuts['Previous Segment'] == ['Ctrl+,']
