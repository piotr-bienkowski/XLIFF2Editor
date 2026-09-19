"""
Results-dialog behaviour and crash-safety of the review.

Covers the three things that went wrong in real use: the progress dialog being
torn down while a progress update was still on the stack, results existing only
in memory, and suggestions being read-only.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

pytest.importorskip('PyQt6')
from PyQt6.QtCore import Qt                                    # noqa: E402
from PyQt6.QtWidgets import (                                  # noqa: E402
    QApplication, QProgressDialog, QTableWidgetSelectionRange,
)

from tm_review_ui import TMReviewResultsDialog                 # noqa: E402


@pytest.fixture(scope='module')
def app():
    return QApplication.instance() or QApplication([])


def _results():
    return [
        (10, {'verdict': 'FIX', 'suggestion': 'Minimalny czas dzialania',
              'reason': 'TM term', 'source': 'Minimum operate time',
              'target': 'Minimalny czas pracy', 'close': [], 'related': []}),
        (20, {'verdict': 'CHECK', 'suggestion': '', 'reason': 'ambiguous',
              'source': 'Rated current 140 A', 'target': 'Prad 240 A',
              'close': [], 'related': []}),
    ]


@pytest.fixture
def dialog(app):
    return TMReviewResultsDialog(None, _results(), reviewed=60,
                                 usage_summary='8 calls')


# ── which rows can be applied ─────────────────────────────────────────────────

def test_fix_row_is_preselected(dialog):
    assert dialog.selected_fixes() == [(10, 'Minimalny czas dzialania')]


def test_check_row_without_a_suggestion_is_not_tickable(dialog):
    flags = dialog.table.item(1, 0).flags()
    assert not (flags & Qt.ItemFlag.ItemIsUserCheckable)


# ── editing ───────────────────────────────────────────────────────────────────

def test_suggestion_cell_is_editable(dialog):
    assert dialog.table.item(0, 5).flags() & Qt.ItemFlag.ItemIsEditable


@pytest.mark.parametrize('column', [1, 2, 3, 4, 6])
def test_other_cells_are_read_only_but_selectable(dialog, column):
    """Read-only so the report cannot be corrupted, selectable so it can be copied."""
    flags = dialog.table.item(0, column).flags()
    assert not (flags & Qt.ItemFlag.ItemIsEditable)
    assert flags & Qt.ItemFlag.ItemIsSelectable


def test_edited_suggestion_is_what_gets_applied(dialog):
    dialog.table.item(0, 5).setText('Minimalny czas zadzialania')
    assert dialog.selected_fixes() == [(10, 'Minimalny czas zadzialania')]


def test_typing_a_fix_makes_a_check_row_applicable(dialog):
    dialog.table.item(1, 5).setText('Prad znamionowy 140 A')
    assert dialog.table.item(1, 0).flags() & Qt.ItemFlag.ItemIsUserCheckable
    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    assert (20, 'Prad znamionowy 140 A') in dialog.selected_fixes()


def test_clearing_a_suggestion_unticks_it(dialog):
    dialog.table.item(1, 5).setText('Prad znamionowy 140 A')
    dialog.table.item(1, 0).setCheckState(Qt.CheckState.Checked)
    dialog.table.item(1, 5).setText('   ')
    assert all(row != 20 for row, _ in dialog.selected_fixes())


def test_whitespace_only_suggestion_is_not_applied(dialog):
    dialog.table.item(0, 5).setText('   ')
    assert dialog.selected_fixes() == []


def test_select_none_clears_everything(dialog):
    dialog._set_all(Qt.CheckState.Unchecked)
    assert dialog.selected_fixes() == []


# ── copying ───────────────────────────────────────────────────────────────────

def test_copy_selection_yields_tab_separated_text(dialog, app):
    dialog.table.setRangeSelected(QTableWidgetSelectionRange(0, 3, 1, 4), True)
    dialog._copy_selection()
    assert app.clipboard().text() == (
        'Minimum operate time\tMinimalny czas pracy\n'
        'Rated current 140 A\tPrad 240 A'
    )


def test_copy_with_no_selection_is_harmless(dialog):
    dialog.table.clearSelection()
    dialog._copy_selection()


# ── crash safety ──────────────────────────────────────────────────────────────

def test_progress_update_survives_the_dialog_being_torn_down(app):
    """
    QProgressDialog.setValue() pumps the event loop on a modal dialog, so the
    finish handler could run — and clear review_progress — while a progress
    update was still on the stack. That aborted the whole process.
    """
    import Xedaibt
    editor = Xedaibt.XLIFFEditor()
    progress = QProgressDialog('Reviewing...', 'Cancel', 0, 10, editor)
    progress.setWindowModality(Qt.WindowModality.WindowModal)
    editor.review_progress = progress

    original = progress.setValue

    def clearing_set_value(value):
        editor.review_progress = None
        original(value)

    progress.setValue = clearing_set_value
    editor._on_review_progress(5, 10, 'Reviewing segments')       # must not raise


def test_progress_update_with_no_dialog_is_harmless(app):
    import Xedaibt
    editor = Xedaibt.XLIFFEditor()
    editor.review_progress = None
    editor._on_review_progress(5, 10, 'Reviewing segments')


# ── persistence ───────────────────────────────────────────────────────────────

def test_results_survive_a_crash(app, tmp_path, monkeypatch):
    """A run costs an hour and real money; it must outlive the process."""
    import Xedaibt
    editor = Xedaibt.XLIFFEditor()
    editor.xliff_file = str(tmp_path / 'job.xlf')
    editor.segments = [{'source': 'Minimum operate time',
                        'target': 'Minimalny czas pracy'}]
    monkeypatch.setattr(editor, '_review_recovery_path',
                        lambda: tmp_path / 'job.review.json')
    editor._review_results = []
    editor._review_all = {}
    editor._review_reviewed_count = 60
    editor._review_usage_summary = '8 calls'
    editor._on_segment_reviewed(0, {'verdict': 'FIX', 'suggestion': 'Nowy',
                                    'reason': 'x', 'close': [], 'related': []})
    editor._save_review_results()

    assert (tmp_path / 'job.review.json').exists()

    reloaded = editor._load_review_results()
    assert reloaded['reviewed'] == 60
    assert reloaded['results'][0][0] == 0
    assert reloaded['results'][0][1]['suggestion'] == 'Nowy'

    editor._clear_review_results()
    assert editor._load_review_results() is None


def test_loading_absent_or_corrupt_results_returns_none(app, tmp_path, monkeypatch):
    import Xedaibt
    editor = Xedaibt.XLIFFEditor()
    path = tmp_path / 'job.review.json'
    monkeypatch.setattr(editor, '_review_recovery_path', lambda: path)
    assert editor._load_review_results() is None

    path.write_text('{ not json', encoding='utf-8')
    assert editor._load_review_results() is None

    path.write_text('{"results": []}', encoding='utf-8')
    assert editor._load_review_results() is None


def test_saving_never_raises_when_the_path_is_unwritable(app, monkeypatch):
    """A failed recovery write must not take the review down with it."""
    import Xedaibt
    editor = Xedaibt.XLIFFEditor()
    editor._review_results = []
    monkeypatch.setattr(editor, '_review_recovery_path',
                        lambda: Path('/proc/nonexistent/job.review.json'))
    editor._save_review_results()


# ── resumable progress ────────────────────────────────────────────────────────
#
# A review is billed per segment, so an interrupted run must not have to pay to
# re-judge what it already judged. Clean verdicts are therefore persisted too,
# and flushed every few segments rather than at the end.

def _editor(tmp_path, monkeypatch, app, segments=3):
    import Xedaibt
    editor = Xedaibt.XLIFFEditor()
    editor.xliff_file = str(tmp_path / 'job.xlf')
    editor.segments = [{'source': f'src {i}', 'target': f'tgt {i}'}
                       for i in range(segments)]
    monkeypatch.setattr(editor, '_review_recovery_path',
                        lambda: tmp_path / 'job.review.json')
    editor._review_results = []
    editor._review_all = {}
    editor._review_unsaved = 0
    editor._review_reviewed_count = 0
    editor._review_usage_summary = ''
    return editor


def _verdict(kind='OK'):
    return {'verdict': kind, 'suggestion': 'x' if kind == 'FIX' else '',
            'reason': 'r', 'close': [], 'related': []}


def test_clean_verdicts_are_persisted_too(app, tmp_path, monkeypatch):
    """Without them a resumed run would re-review, and re-pay for, clean segments."""
    editor = _editor(tmp_path, monkeypatch, app)
    for row in range(3):
        editor._on_segment_reviewed(row, _verdict('OK'))
    editor._save_review_results()

    reloaded = editor._load_review_results()
    assert set(reloaded['reviewed_rows']) == {0, 1, 2}
    assert reloaded['results'] == []            # nothing flagged, nothing to triage


def test_flagged_and_clean_are_tracked_separately(app, tmp_path, monkeypatch):
    editor = _editor(tmp_path, monkeypatch, app)
    editor._on_segment_reviewed(0, _verdict('OK'))
    editor._on_segment_reviewed(1, _verdict('FIX'))
    editor._save_review_results()

    reloaded = editor._load_review_results()
    assert set(reloaded['reviewed_rows']) == {0, 1}
    assert [row for row, _ in reloaded['results']] == [1]


def test_results_are_flushed_every_few_segments(app, tmp_path, monkeypatch):
    """The window a crash can destroy is bounded by REVIEW_SAVE_EVERY."""
    import Xedaibt
    editor = _editor(tmp_path, monkeypatch, app, segments=Xedaibt.REVIEW_SAVE_EVERY + 1)
    for row in range(Xedaibt.REVIEW_SAVE_EVERY - 1):
        editor._on_segment_reviewed(row, _verdict('OK'))
    assert editor._load_review_results() is None        # not flushed yet

    editor._on_segment_reviewed(Xedaibt.REVIEW_SAVE_EVERY - 1, _verdict('OK'))
    reloaded = editor._load_review_results()
    assert reloaded is not None
    assert len(reloaded['reviewed_rows']) == Xedaibt.REVIEW_SAVE_EVERY


def test_flush_resets_the_unsaved_counter(app, tmp_path, monkeypatch):
    import Xedaibt
    editor = _editor(tmp_path, monkeypatch, app, segments=Xedaibt.REVIEW_SAVE_EVERY + 2)
    for row in range(Xedaibt.REVIEW_SAVE_EVERY):
        editor._on_segment_reviewed(row, _verdict('OK'))
    assert editor._review_unsaved == 0


def test_save_never_raises_without_prior_initialisation(app, tmp_path, monkeypatch):
    """_on_segment_reviewed must not depend on attributes being pre-created."""
    import Xedaibt
    editor = Xedaibt.XLIFFEditor()
    editor.xliff_file = str(tmp_path / 'job.xlf')
    editor.segments = [{'source': 's', 'target': 't'}]
    monkeypatch.setattr(editor, '_review_recovery_path',
                        lambda: tmp_path / 'job.review.json')
    editor._on_segment_reviewed(0, _verdict('FIX'))     # no attributes set up
    assert 0 in editor._review_all
