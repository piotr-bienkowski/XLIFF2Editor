# Filter Bar — Design Spec

**Date:** 2026-05-28  
**File:** `Xedaibt.py`  
**Approach:** `setRowHidden` on existing `QTableWidget`

---

## Summary

Add a horizontal filter bar above the segment table. Users can filter visible rows by source text, target text, or both, with optional regex support and AND/OR logic.

---

## UI Layout

A single `QWidget` (`filter_bar`) with a `QHBoxLayout`, inserted at the top of the central widget layout. `main_layout` changes from `QHBoxLayout` to `QVBoxLayout`; `filter_bar` is added first, then the existing `QSplitter`.

```
[ Source: _____________ ] [ Target: _____________ ] [ AND ▾ ] [ ☐ Regex ] [ 🔍 ] [ ✕ ]
```

| Widget | Type | Details |
|--------|------|---------|
| `self.filter_source` | `QLineEdit` | Placeholder: "Filter source…" |
| `self.filter_target` | `QLineEdit` | Placeholder: "Filter target…" |
| `self.filter_logic` | `QComboBox` | Items: `["AND", "OR"]` |
| `self.filter_regex` | `QCheckBox` | Label: "Regex" |
| Filter button | `QPushButton` | Text: "🔍"; triggers `apply_filter()` |
| Clear button | `QPushButton` | Text: "✕"; triggers `clear_filter()` |

`Return`/`Enter` in either `QLineEdit` also triggers `apply_filter()`.

---

## Filter Logic

### `apply_filter()`

1. Read `src_pat` from `self.filter_source.text()` and `trg_pat` from `self.filter_target.text()`
2. If regex checked, compile both non-empty patterns with `re.compile(pat, re.IGNORECASE)`; on `re.error` show `QMessageBox.warning` and return
3. Iterate `range(self.table.rowCount())`:
   - Get `src_text = self.table.item(row, 2).text()`
   - Get `trg_text = self.table.item(row, 3).text()`
   - Compute `src_match` and `trg_match` (only for non-empty patterns):
     - Plain text: `pat.lower() in text.lower()`
     - Regex: `bool(compiled.search(text))`
   - Visibility rules:
     - Both patterns empty → visible
     - Only source pattern → visible if `src_match`
     - Only target pattern → visible if `trg_match`
     - Both patterns → visible if `src_match AND trg_match` (AND mode) or `src_match OR trg_match` (OR mode)
4. Call `self.table.setRowHidden(row, not visible)`

### `clear_filter()`

1. `self.filter_source.clear()`
2. `self.filter_target.clear()`
3. `for row in range(self.table.rowCount()): self.table.setRowHidden(row, False)`

---

## Integration Points

| Location | Change |
|----------|--------|
| `init_ui()` | Change `main_layout` to `QVBoxLayout`; build `filter_bar` widget; connect signals |
| `populate_table()` | Call `clear_filter()` at the end — opening a file resets the filter |
| `copy_all_sources_to_targets()` | Add `if self.table.isRowHidden(row): continue` guard |

No changes required to: `on_item_changed`, `on_cell_changed`, AI translate, save, export, or any other method — they operate on `self.segments` or specific rows, not visible-row ranges.

---

## Error Handling

- Invalid regex pattern: `QMessageBox.warning(self, "Invalid Regex", str(e))` then return without filtering
- Empty table (no file open): `apply_filter()` is a no-op (loop over 0 rows)

---

## Testing Checklist

- [ ] Plain text filter: source only, target only, both AND, both OR
- [ ] Regex filter: valid pattern matches correctly
- [ ] Regex filter: invalid pattern shows warning, filter not applied
- [ ] Clear button restores all rows
- [ ] Opening a new file clears the filter
- [ ] `copy_all_sources_to_targets` skips hidden rows
- [ ] Filter survives a target edit (hidden rows stay hidden after `itemChanged`)
- [ ] `Return` in either line edit triggers filter
