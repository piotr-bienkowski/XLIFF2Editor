# Lazy Row Sizing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate scroll and edit sluggishness with large XLIFF files by replacing global `ResizeToContents` row sizing with lazy on-demand sizing of only the visible rows.

**Architecture:** Switch the vertical header from `ResizeToContents` to `Fixed` with a 60 px default. A new `_resize_visible_rows()` method sizes only the rows currently in the viewport. It is triggered on scroll, after `populate_table()`, and after font-size change. Individual edits trigger `resizeRowToContents()` for just the changed row.

**Tech Stack:** PyQt6, Python 3.13

---

## File Map

| File | Change |
|------|--------|
| `Xedaibt.py` | All changes — `init_ui()`, new `_resize_visible_rows()`, `populate_table()`, `on_item_changed()`, `apply_font_size()` |

No new files. No new tests (this feature is Qt UI performance behaviour — not unit-testable without a full display; manual verification steps are provided instead).

---

### Task 1: Switch to Fixed mode and add `_resize_visible_rows()`

**Files:**
- Modify: `Xedaibt.py` line 1172 (vertical header setup in `init_ui()`)
- Modify: `Xedaibt.py` — add `_resize_visible_rows()` method to `XLIFFEditor`

- [ ] **Step 1: Replace `ResizeToContents` with `Fixed` in `init_ui()`**

Find line 1172:
```python
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().hide()
```

Replace with:
```python
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.table.verticalHeader().setDefaultSectionSize(60)
        self.table.verticalHeader().hide()
        self.table.verticalScrollBar().valueChanged.connect(self._resize_visible_rows)
```

- [ ] **Step 2: Add `_resize_visible_rows()` to `XLIFFEditor`**

Insert this method immediately after `clear_filter()` (currently ending around line 1822):

```python
    def _resize_visible_rows(self):
        vp = self.table.viewport()
        first = self.table.rowAt(0)
        last = self.table.rowAt(vp.height() - 1)
        if first < 0:
            return
        if last < 0:
            last = self.table.rowCount() - 1
        for row in range(first, last + 1):
            if not self.table.isRowHidden(row):
                self.table.resizeRowToContents(row)
```

- [ ] **Step 3: Verify the app launches without errors**

```bash
cd /home/piotr/XLIFF2Editor && timeout 3 python -m XLIFF2Editor 2>&1 || true
```

Expected: no Python traceback. A clean exit or timeout (code 124) both indicate success.

- [ ] **Step 4: Commit**

```bash
cd /home/piotr/XLIFF2Editor && git add Xedaibt.py && git commit -m "perf: switch to Fixed row mode with lazy _resize_visible_rows()"
```

---

### Task 2: Wire `_resize_visible_rows()` into populate, edit, and font-size paths

**Files:**
- Modify: `Xedaibt.py` — three targeted edits

- [ ] **Step 1: Call `_resize_visible_rows()` at end of `populate_table()`**

Find the end of `populate_table()` (currently lines 1793–1794):
```python
        self.table.itemChanged.connect(self.on_item_changed)
        self.clear_filter()
```

Change to:
```python
        self.table.itemChanged.connect(self.on_item_changed)
        self.clear_filter()
        self._resize_visible_rows()
```

- [ ] **Step 2: Resize just the edited row in `on_item_changed()`**

Find `on_item_changed()` (line 2012):
```python
    def on_item_changed(self, item):
        if item.column() == 3:  # Column 3 is now Target
            row = item.row()
            val = item.text()
            self.segments[row]['target'] = val
            self.is_modified = True
            count = self._propagate_to_identical(self.segments[row]['source'], val, row)
            if count:
                self.statusBar().showMessage(f"Propagated to {count} identical segment(s).", 3000)
```

Change to:
```python
    def on_item_changed(self, item):
        if item.column() == 3:  # Column 3 is now Target
            row = item.row()
            val = item.text()
            self.segments[row]['target'] = val
            self.is_modified = True
            self.table.resizeRowToContents(row)
            count = self._propagate_to_identical(self.segments[row]['source'], val, row)
            if count:
                self.statusBar().showMessage(f"Propagated to {count} identical segment(s).", 3000)
```

- [ ] **Step 3: Fix `apply_font_size()` to reset rows then resize visible**

Find `apply_font_size()` (line 1495):
```python
    def apply_font_size(self):
        """Apply the current font size to all widgets"""
        font = QFont()
        font.setPointSize(self.font_size)
        
        # Apply to application (menus)
        QApplication.instance().setFont(font)
        
        # Apply to table
        self.table.setFont(font)
        
        # Apply to TM list
        self.tm_list.setFont(font)
        
        # Force table to refresh with new font
        self.table.resizeRowsToContents()
```

Change to:
```python
    def apply_font_size(self):
        """Apply the current font size to all widgets"""
        font = QFont()
        font.setPointSize(self.font_size)
        
        # Apply to application (menus)
        QApplication.instance().setFont(font)
        
        # Apply to table
        self.table.setFont(font)
        
        # Apply to TM list
        self.tm_list.setFont(font)
        
        # Reset all rows to font-size-aware default, then size visible rows lazily
        default_h = max(60, self.font_size * 6)
        self.table.verticalHeader().setDefaultSectionSize(default_h)
        for row in range(self.table.rowCount()):
            self.table.setRowHeight(row, default_h)
        self._resize_visible_rows()
```

- [ ] **Step 4: Run the full test suite**

```bash
cd /home/piotr/XLIFF2Editor && python -m pytest -v 2>&1 | tail -5
```

Expected: 30 passed, 0 failures.

- [ ] **Step 5: Manual smoke test**

Launch the app and open a large XLIFF file (e.g. one with 512 segments):
```bash
cd /home/piotr/XLIFF2Editor && python -m XLIFF2Editor
```

Verify:
- Rows in the initial viewport are correctly sized to their content on load
- Scrolling down reveals rows that resize to their content as they enter view
- Editing a target cell resizes just that row
- Options → Change Font Size updates visible rows immediately; rows not yet scrolled to will resize when they come into view

- [ ] **Step 6: Commit**

```bash
cd /home/piotr/XLIFF2Editor && git add Xedaibt.py && git commit -m "perf: wire lazy row sizing into populate, edit, and font-size paths"
```
