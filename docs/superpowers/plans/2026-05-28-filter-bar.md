# Filter Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a source/target filter bar above the segment table in XLIFF2Editor, with AND/OR logic, regex support, and instant row hiding.

**Architecture:** `setRowHidden` approach — a horizontal filter bar widget is inserted above the QSplitter by changing `main_layout` from `QHBoxLayout` to `QVBoxLayout`. Filter matching logic is extracted as a module-level function `_filter_matches()` for testability. Two new methods `apply_filter()` and `clear_filter()` are added to `XLIFFEditor`. `populate_table()` resets the filter on file open; `copy_all_sources_to_targets()` skips hidden rows.

**Tech Stack:** PyQt6, Python 3.13, pytest

---

## File Map

| File | Change |
|------|--------|
| `Xedaibt.py` | Add `QCheckBox` import; add module-level `_filter_matches()`; restructure `init_ui()` layout; add `apply_filter()` and `clear_filter()` methods; patch `populate_table()` and `copy_all_sources_to_targets()` |
| `tests/test_filter.py` | New — unit tests for `_filter_matches()` |

---

### Task 1: Add `_filter_matches()` and unit tests

**Files:**
- Modify: `Xedaibt.py` (insert before `class XLIFFEditor` at line 895)
- Create: `tests/test_filter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_filter.py`:

```python
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from Xedaibt import _filter_matches


def test_no_filter_always_visible():
    assert _filter_matches("hello", "world", None, None, True) is True


def test_source_plain_match():
    assert _filter_matches("Hello World", "anything", "hello", None, True) is True


def test_source_plain_case_insensitive():
    assert _filter_matches("HELLO WORLD", "anything", "hello", None, True) is True


def test_source_plain_no_match():
    assert _filter_matches("Hello World", "anything", "xyz", None, True) is False


def test_target_plain_match():
    assert _filter_matches("anything", "Cześć świat", None, "cześć", True) is True


def test_target_plain_no_match():
    assert _filter_matches("anything", "Cześć świat", None, "xyz", True) is False


def test_both_and_both_match():
    assert _filter_matches("Hello", "Cześć", "hello", "cześć", True) is True


def test_both_and_only_source_matches():
    assert _filter_matches("Hello", "Cześć", "hello", "xyz", True) is False


def test_both_or_only_source_matches():
    assert _filter_matches("Hello", "Cześć", "hello", "xyz", False) is True


def test_both_or_neither_matches():
    assert _filter_matches("Hello", "Cześć", "xyz", "abc", False) is False


def test_regex_source_match():
    pat = re.compile(r"hel+o", re.IGNORECASE)
    assert _filter_matches("Hello World", "anything", pat, None, True) is True


def test_regex_source_no_match():
    pat = re.compile(r"^World", re.IGNORECASE)
    assert _filter_matches("Hello World", "anything", pat, None, True) is False


def test_regex_target_match():
    pat = re.compile(r"\d+", re.IGNORECASE)
    assert _filter_matches("anything", "segment 42", None, pat, True) is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/piotr/XLIFF2Editor && python -m pytest tests/test_filter.py -v 2>&1 | head -20
```

Expected: `ImportError` — `_filter_matches` not yet defined.

- [ ] **Step 3: Add `_filter_matches()` to `Xedaibt.py`**

Insert this function immediately before `class XLIFFEditor(QMainWindow):` (line 895):

```python
def _filter_matches(src_text: str, trg_text: str, src_pat, trg_pat, use_and: bool) -> bool:
    """Return True if a segment row should be visible given the active filter.

    src_pat / trg_pat: compiled re.Pattern for regex mode, plain str for
    case-insensitive contains, or None for no filter on that column.
    use_and: True = both non-None patterns must match; False = either suffices.
    """
    def hit(text: str, pat) -> bool:
        if isinstance(pat, str):
            return pat.lower() in text.lower()
        return bool(pat.search(text))

    if src_pat is None and trg_pat is None:
        return True
    if src_pat is not None and trg_pat is None:
        return hit(src_text, src_pat)
    if trg_pat is not None and src_pat is None:
        return hit(trg_text, trg_pat)
    sm, tm = hit(src_text, src_pat), hit(trg_text, trg_pat)
    return (sm and tm) if use_and else (sm or tm)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /home/piotr/XLIFF2Editor && python -m pytest tests/test_filter.py -v
```

Expected: 13 tests PASS, 0 failures.

- [ ] **Step 5: Commit**

```bash
cd /home/piotr/XLIFF2Editor && git add Xedaibt.py tests/test_filter.py && git commit -m "feat: add _filter_matches() with unit tests"
```

---

### Task 2: Add `QCheckBox` import and build filter bar UI

**Files:**
- Modify: `Xedaibt.py` (imports block at line 7; `init_ui()` around line 1103)

- [ ] **Step 1: Add `QCheckBox` to the PyQt6 imports**

In `Xedaibt.py` lines 7–12, the current import block ends with `QSizePolicy)`. Add `QCheckBox`:

Old:
```python
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QMessageBox,
                             QListWidget, QSplitter, QHeaderView, QAbstractItemView,
                             QProgressDialog, QStyledItemDelegate, QTextEdit, QPlainTextEdit,
                             QInputDialog, QDialog, QLabel, QLineEdit, QPushButton, QFormLayout,
                             QMenu, QColorDialog, QToolBar, QComboBox, QSizePolicy)
```

New:
```python
from PyQt6.QtWidgets import (QApplication, QMainWindow, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, QMessageBox,
                             QListWidget, QSplitter, QHeaderView, QAbstractItemView,
                             QProgressDialog, QStyledItemDelegate, QTextEdit, QPlainTextEdit,
                             QInputDialog, QDialog, QLabel, QLineEdit, QPushButton, QFormLayout,
                             QMenu, QColorDialog, QToolBar, QComboBox, QSizePolicy, QCheckBox)
```

- [ ] **Step 2: Replace the central widget layout block in `init_ui()`**

Find this exact block (around line 1103):

```python
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        splitter = QSplitter(Qt.Orientation.Horizontal)
```

Replace with:

```python
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Filter bar
        filter_bar = QWidget()
        filter_layout = QHBoxLayout(filter_bar)
        filter_layout.setContentsMargins(4, 2, 4, 2)
        filter_layout.addWidget(QLabel("Source:"))
        self.filter_source = QLineEdit()
        self.filter_source.setPlaceholderText("Filter source…")
        self.filter_source.returnPressed.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_source)
        filter_layout.addWidget(QLabel("Target:"))
        self.filter_target = QLineEdit()
        self.filter_target.setPlaceholderText("Filter target…")
        self.filter_target.returnPressed.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_target)
        self.filter_logic = QComboBox()
        self.filter_logic.addItems(["AND", "OR"])
        filter_layout.addWidget(self.filter_logic)
        self.filter_regex = QCheckBox("Regex")
        filter_layout.addWidget(self.filter_regex)
        btn_filter = QPushButton("🔍")
        btn_filter.setToolTip("Apply filter")
        btn_filter.clicked.connect(self.apply_filter)
        filter_layout.addWidget(btn_filter)
        btn_clear = QPushButton("✕")
        btn_clear.setToolTip("Clear filter")
        btn_clear.clicked.connect(self.clear_filter)
        filter_layout.addWidget(btn_clear)
        filter_layout.addStretch()
        main_layout.addWidget(filter_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
```

The lines after (`self.table = QTableWidget()` through `main_layout.addWidget(splitter)`) are unchanged.

- [ ] **Step 3: Verify the app launches**

```bash
cd /home/piotr/XLIFF2Editor && python -m XLIFF2Editor
```

Expected: window opens, filter bar visible above the table with Source/Target fields, AND/OR dropdown, Regex checkbox, 🔍 and ✕ buttons. Close the window.

- [ ] **Step 4: Commit**

```bash
cd /home/piotr/XLIFF2Editor && git add Xedaibt.py && git commit -m "feat: add filter bar UI to init_ui()"
```

---

### Task 3: Implement `apply_filter()` and `clear_filter()`

**Files:**
- Modify: `Xedaibt.py` (add two methods to `XLIFFEditor`, after `populate_table()` ~line 1739)

- [ ] **Step 1: Add both methods to `XLIFFEditor`**

Insert immediately after the `populate_table()` method (after the `self.table.itemChanged.connect(self.on_item_changed)` line that ends it):

```python
    def apply_filter(self):
        src_text = self.filter_source.text()
        trg_text = self.filter_target.text()
        use_regex = self.filter_regex.isChecked()
        use_and = self.filter_logic.currentText() == "AND"

        try:
            src_pat = re.compile(src_text, re.IGNORECASE) if (src_text and use_regex) else (src_text or None)
            trg_pat = re.compile(trg_text, re.IGNORECASE) if (trg_text and use_regex) else (trg_text or None)
        except re.error as e:
            QMessageBox.warning(self, "Invalid Regex", str(e))
            return

        for row in range(self.table.rowCount()):
            src = self.table.item(row, 2).text() if self.table.item(row, 2) else ""
            trg = self.table.item(row, 3).text() if self.table.item(row, 3) else ""
            self.table.setRowHidden(row, not _filter_matches(src, trg, src_pat, trg_pat, use_and))

    def clear_filter(self):
        self.filter_source.clear()
        self.filter_target.clear()
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
```

- [ ] **Step 2: Smoke test — plain text filter**

Launch the app, open `test_english.xliff`. Type a word from a known segment in the Source field, press Enter. Verify only matching rows are shown. Press ✕ to clear — all rows return.

- [ ] **Step 3: Smoke test — AND/OR logic**

With the file open, type a word in Source, a different word in Target, switch to OR mode, press 🔍. Verify rows matching either field appear. Switch to AND — verify only rows matching both remain.

- [ ] **Step 4: Smoke test — regex error handling**

Check the Regex checkbox. Type `[invalid` in the Source field. Press 🔍. Verify a warning dialog appears with the regex error text, and no rows disappear.

- [ ] **Step 5: Commit**

```bash
cd /home/piotr/XLIFF2Editor && git add Xedaibt.py && git commit -m "feat: implement apply_filter() and clear_filter()"
```

---

### Task 4: Integration — `populate_table()` and `copy_all_sources_to_targets()`

**Files:**
- Modify: `Xedaibt.py` (two targeted single-line edits)

- [ ] **Step 1: Call `clear_filter()` at end of `populate_table()`**

Find the closing line of `populate_table()` (currently ~line 1739):

```python
        self.table.itemChanged.connect(self.on_item_changed)
```

Change to:

```python
        self.table.itemChanged.connect(self.on_item_changed)
        self.clear_filter()
```

- [ ] **Step 2: Add hidden-row guard to `copy_all_sources_to_targets()`**

Find the locked-segment skip inside the loop (currently ~line 2353):

```python
                # Skip locked segments
                if self.segments[row].get('locked', False):
                    skipped_count += 1
                    continue
```

Change to:

```python
                # Skip hidden (filtered-out) and locked segments
                if self.table.isRowHidden(row):
                    continue
                if self.segments[row].get('locked', False):
                    skipped_count += 1
                    continue
```

- [ ] **Step 3: Run the full test suite**

```bash
cd /home/piotr/XLIFF2Editor && python -m pytest -v
```

Expected: all tests pass (13 filter tests + all pre-existing tests).

- [ ] **Step 4: Integration smoke test**

Launch the app, open `test_english.xliff`, apply a source filter so only some rows are visible. Run Tasks → Copy All Sources to Targets. Confirm only visible rows were affected (check a hidden row's target — it should be unchanged). Close app.

- [ ] **Step 5: Final commit**

```bash
cd /home/piotr/XLIFF2Editor && git add Xedaibt.py && git commit -m "feat: integrate filter with populate_table and copy_all_sources_to_targets"
```
