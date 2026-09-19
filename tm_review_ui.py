#!/usr/bin/env python3
"""
PyQt6 front end for the HybridTM batch review.

Three pieces:

* ``HybridTMLookupThread`` -- background lookup for the side panel, so selecting
  a row never blocks the UI on a ~0.5 s search.
* ``TMReviewThread``       -- the batch pass: prefetch every source from
  HybridTM, then one LLM call per segment.
* ``TMReviewSetupDialog`` / ``TMReviewResultsDialog`` -- configure the run and
  triage what comes back.

Nothing here edits a segment. The results dialog hands the caller a list of
(row, suggestion) pairs and the caller applies them, so a review can always be
dismissed without touching the file.
"""

from __future__ import annotations

import time

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
)

VERDICT_COLOURS = {
    'FIX': QColor(180, 70, 70),
    'CHECK': QColor(180, 140, 60),
    'OK': QColor(90, 140, 90),
}


# ── side-panel lookup ─────────────────────────────────────────────────────────

class HybridTMLookupThread(QThread):
    """One HybridTM search, reported back with the row it was started for."""

    done = pyqtSignal(int, list)      # row, matches
    failed = pyqtSignal(int, str)

    def __init__(self, client, row, text, src_lang, tgt_lang,
                 similarity=55, limit=5):
        super().__init__()
        self.client = client
        self.row = row
        self.text = text
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.similarity = similarity
        self.limit = limit

    def run(self):
        try:
            matches = self.client.search(self.text, self.src_lang, self.tgt_lang,
                                         self.similarity, self.limit)
            self.done.emit(self.row, matches)
        except Exception as exc:                     # noqa: BLE001 - reported to UI
            self.failed.emit(self.row, str(exc))


# ── batch review ──────────────────────────────────────────────────────────────

class TMReviewThread(QThread):
    """
    Review a list of segments against HybridTM plus an LLM.

    ``jobs`` is a list of (row, source, target). Progress is reported in two
    phases because the prefetch is fast and the model calls are not.
    """

    progress = pyqtSignal(int, int, str)     # done, total, phase
    reviewed = pyqtSignal(int, dict)         # row, result
    finished_ok = pyqtSignal(int, int, str)  # reviewed, flagged, usage summary
    failed = pyqtSignal(str)

    def __init__(self, client, jobs, src_lang, tgt_lang, api_key, model,
                 domain='', glossary=None):
        super().__init__()
        self.client = client
        self.jobs = jobs
        self.src_lang = src_lang
        self.tgt_lang = tgt_lang
        self.api_key = api_key
        self.model = model
        self.domain = domain
        self.glossary = glossary or {}
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        import tm_review as review
        try:
            # Phase 1 -- one HybridTM lookup per distinct source.
            sources = [source for _, source, _ in self.jobs]
            self.progress.emit(0, len(self.jobs), 'Searching translation memory')
            matches_by_source = self.client.batch_search(
                sources, self.src_lang, self.tgt_lang,
                similarity=review.HTM_SEARCH_FLOOR, limit=review.HTM_SEARCH_LIMIT,
                progress=lambda done, total: self.progress.emit(
                    done, total, 'Searching translation memory'),
                should_cancel=lambda: self._cancelled,
            )
            if self._cancelled:
                self.finished_ok.emit(0, 0)
                return

            # Phase 2 -- one model call per segment.
            #
            # The system prompt is built once and never varies, so OpenRouter can
            # cache its prefix across the run. The glossary is cut down to the
            # terms this job actually uses before it goes in: an unfiltered
            # termbase re-sent on every call is what dominates the bill.
            client = review.make_client(self.api_key)
            glossary = review.filter_glossary_to_sources(self.glossary, sources)
            system = review.build_system_prompt(
                self.src_lang, self.tgt_lang, review.format_glossary(glossary),
                self.domain)

            usage = review.Usage()
            # Identical source+target pairs get one call, not one per occurrence.
            # Technical documentation repeats itself heavily -- on the ABB job a
            # fifth of the in-scope segments are exact repeats of another.
            answered = {}
            done = flagged = 0
            called = False

            for row, source, target in self.jobs:
                if self._cancelled:
                    break
                key = (source, target)
                if key in answered:
                    result = answered[key]
                    usage.cache_hits += 1
                else:
                    if called:
                        time.sleep(review.MIN_DELAY)
                    try:
                        result = review.review_segment(
                            client, source, target, matches_by_source.get(source, []),
                            system, model=self.model, usage=usage)
                    except Exception as exc:         # noqa: BLE001
                        result = {'verdict': 'CHECK', 'suggestion': '',
                                  'reason': f'review failed: {exc}',
                                  'close': [], 'related': []}
                    called = True
                    answered[key] = result
                done += 1
                if result['verdict'] != 'OK':
                    flagged += 1
                # Every verdict is emitted, clean ones included: the caller
                # persists them so an interrupted run can resume instead of
                # paying to re-review segments it already judged.
                self.reviewed.emit(row, result)
                self.progress.emit(done, len(self.jobs), 'Reviewing segments')

            self.finished_ok.emit(done, flagged, usage.summary())
        except Exception as exc:                     # noqa: BLE001
            self.failed.emit(str(exc))


# ── dialogs ───────────────────────────────────────────────────────────────────

class TMReviewSetupDialog(QDialog):
    """Pick the instance, model and scope for a batch review."""

    SCOPES = [
        ('Unconfirmed segments only', 'unconfirmed'),
        ('All translated segments', 'translated'),
        ('Visible rows only (respects the filter)', 'visible'),
    ]

    def __init__(self, parent=None, instances=None, instance='', model='',
                 domain='', src_lang='en-US', tgt_lang='pl-PL', counts=None):
        super().__init__(parent)
        self.setWindowTitle('HybridTM Batch Review')
        layout = QFormLayout(self)

        self.instance = QComboBox()
        self.instance.setEditable(True)
        for name in (instances or []):
            self.instance.addItem(name)
        if instance:
            self.instance.setCurrentText(instance)

        self.model = QLineEdit(model or 'google/gemini-2.5-flash-lite')
        self.src_lang = QLineEdit(src_lang)
        self.tgt_lang = QLineEdit(tgt_lang)
        self.domain = QLineEdit(domain)
        self.domain.setPlaceholderText('e.g. ABB protection relay documentation')

        self.scope = QComboBox()
        for label, key in self.SCOPES:
            suffix = ''
            if counts and key in counts:
                suffix = f'  ({counts[key]} segments)'
            self.scope.addItem(label + suffix, key)

        self.skip_locked = QCheckBox('Skip segments locked in the source tool')
        self.skip_locked.setChecked(True)

        layout.addRow('HybridTM instance:', self.instance)
        layout.addRow('Model (OpenRouter):', self.model)
        layout.addRow('Source language:', self.src_lang)
        layout.addRow('Target language:', self.tgt_lang)
        layout.addRow('Subject matter:', self.domain)
        layout.addRow('Review:', self.scope)
        layout.addRow('', self.skip_locked)

        note = QLabel('100%, 101% and context (CM) matches are never reviewed, '
                      'confirmed or not.\n'
                      'Language codes must match the TM exactly — "en-US" finds '
                      'matches where "en" silently finds none.\n'
                      'One model call per segment is billed to your OpenRouter '
                      'account. Nothing is changed until you apply it.')
        note.setWordWrap(True)
        note.setStyleSheet('color: gray;')
        layout.addRow(note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self):
        return {
            'instance': self.instance.currentText().strip(),
            'model': self.model.text().strip(),
            'src_lang': self.src_lang.text().strip(),
            'tgt_lang': self.tgt_lang.text().strip(),
            'domain': self.domain.text().strip(),
            'scope': self.scope.currentData(),
            'skip_locked': self.skip_locked.isChecked(),
        }


class TMReviewResultsDialog(QDialog):
    """Triage the flagged segments and choose which fixes to apply."""

    COLS = ['Apply', 'Row', 'Verdict', 'Source', 'Current target', 'Suggestion', 'Reason']

    def __init__(self, parent=None, results=None, reviewed=0, usage_summary=''):
        super().__init__(parent)
        self.setWindowTitle('HybridTM Review Results')
        self.resize(1150, 620)
        self.results = results or []

        layout = QVBoxLayout(self)

        fixes = sum(1 for _, r in self.results if r['verdict'] == 'FIX')
        checks = len(self.results) - fixes
        summary = QLabel(f'Reviewed {reviewed} segments — '
                         f'{fixes} with a suggested fix, {checks} to check, '
                         f'{reviewed - len(self.results)} clean.')
        layout.addWidget(summary)

        if usage_summary:
            cost = QLabel(usage_summary)
            cost.setStyleSheet('color: gray;')
            cost.setWordWrap(True)
            layout.addWidget(cost)

        self.table = QTableWidget(len(self.results), len(self.COLS))
        self.table.setHorizontalHeaderLabels(self.COLS)
        # The Suggestion column is editable so a proposal can be corrected before
        # it is applied, and a CHECK row — where the model declined to offer one —
        # can be given a fix by hand. Everything else is read-only but selectable,
        # so source and target text can be copied out with Ctrl+C.
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked |
                                   QAbstractItemView.EditTrigger.SelectedClicked |
                                   QAbstractItemView.EditTrigger.EditKeyPressed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        for index, (row, result) in enumerate(self.results):
            applicable = result['verdict'] == 'FIX' and bool(result['suggestion'])
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
                           if applicable else Qt.ItemFlag.NoItemFlags)
            check.setCheckState(Qt.CheckState.Checked if applicable
                                else Qt.CheckState.Unchecked)
            self.table.setItem(index, 0, check)

            verdict = QTableWidgetItem(result['verdict'])
            verdict.setForeground(VERDICT_COLOURS.get(result['verdict'], QColor(150, 150, 150)))
            row_item = QTableWidgetItem(str(row + 1))
            for item in (row_item, verdict):
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(index, 1, row_item)
            self.table.setItem(index, 2, verdict)
            for column, text in ((3, result.get('source', '')),
                                 (4, result.get('target', ''))):
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.table.setItem(index, column, item)

            suggestion = QTableWidgetItem(result.get('suggestion', ''))
            suggestion.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                                | Qt.ItemFlag.ItemIsEditable)
            suggestion.setToolTip('Double-click to edit before applying')
            self.table.setItem(index, 5, suggestion)

            reason = QTableWidgetItem(result.get('reason', ''))
            tips = []
            for match in result.get('close', [])[:3]:
                tips.append(f'CLOSE {match["best_fuzzy"]}%: {match["source"]} | {match["target"]}')
            for match in result.get('related', [])[:3]:
                tips.append(f'RELATED {match["semantic"]}%: {match["source"]} | {match["target"]}')
            if tips:
                reason.setToolTip('\n'.join(tips))
            reason.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.table.setItem(index, 6, reason)

        self.table.itemChanged.connect(self._on_item_changed)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 55)
        self.table.setColumnWidth(2, 65)
        layout.addWidget(self.table)

        controls = QHBoxLayout()
        for label, state in (('Select all fixes', Qt.CheckState.Checked),
                             ('Select none', Qt.CheckState.Unchecked)):
            button = QPushButton(label)
            button.clicked.connect(lambda _, s=state: self._set_all(s))
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('Apply selected')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_item_changed(self, item):
        """Keep the Apply box in step with an edited suggestion.

        Typing a fix into a CHECK row makes it applicable; clearing a
        suggestion makes it un-tickable again.
        """
        if item.column() != 5:
            return
        check = self.table.item(item.row(), 0)
        if check is None:
            return
        has_text = bool(item.text().strip())
        blocked = self.table.blockSignals(True)
        if has_text:
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        else:
            check.setCheckState(Qt.CheckState.Unchecked)
            check.setFlags(Qt.ItemFlag.NoItemFlags)
        self.table.blockSignals(blocked)

    def _set_all(self, state):
        for index in range(self.table.rowCount()):
            item = self.table.item(index, 0)
            if item.flags() & Qt.ItemFlag.ItemIsUserCheckable:
                item.setCheckState(state)

    def keyPressEvent(self, event):
        """Ctrl+C copies the selected cells as tab-separated text."""
        if event.matches(QKeySequence.StandardKey.Copy):
            self._copy_selection()
            return
        super().keyPressEvent(event)

    def _copy_selection(self):
        ranges = self.table.selectedRanges()
        if not ranges:
            return
        lines = []
        for block in ranges:
            for row in range(block.topRow(), block.bottomRow() + 1):
                cells = []
                for column in range(block.leftColumn(), block.rightColumn() + 1):
                    item = self.table.item(row, column)
                    cells.append(item.text() if item else '')
                lines.append('\t'.join(cells))
        QApplication.clipboard().setText('\n'.join(lines))

    def selected_fixes(self):
        """[(row, suggestion)] for every ticked line, using the edited text."""
        out = []
        for index, (row, _result) in enumerate(self.results):
            check = self.table.item(index, 0)
            cell = self.table.item(index, 5)
            if check is None or cell is None:
                continue
            text = cell.text().strip()
            if check.checkState() == Qt.CheckState.Checked and text:
                out.append((row, text))
        return out
