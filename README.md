# Xliff 2 Editor

## Overview

A PyQt6-based graphical XLIFF editor for professional translation workflows. Supports XLIFF 2.0, 2.1, and 2.2 files. Provides tag-aware editing, AI/MT translation via multiple providers (Claude, Gemini, OpenAI, DeepL), translation memory (TMX) support, spell checking, SDL Trados SDLXLIFF conversion, memoQ MQXLIFF conversion, and automatic light/dark theme switching.

**A note for Windows users: ** To clone this repository, first you need to install the git binary for Windows ([Git Guides - install git · GitHub](https://github.com/git-guides/install-git)) and then open a command line window (cmd) and enter the following:

```

git clone https://github.com/piotr-bienkowski/XLIFF2Editor.git
```

---

## Running the Editor

From any directory:

```bash
python -m XLIFF2Editor
```

Or from inside the `XLIFF2Editor` directory:

```bash
python Xedaibt.py
```

The application detects the system theme at startup and applies light or dark mode automatically. The theme can be toggled manually at any time via **Options → Switch to Light/Dark Theme**.

---

## Dependencies

### Python Packages (Required)

| Package          | Purpose                                               |
| ---------------- | ----------------------------------------------------- |
| `PyQt6`          | GUI framework                                         |
| `beautifulsoup4` | XML/XLIFF parsing                                     |
| `lxml`           | XML processing (used by BeautifulSoup and converters) |
| `fuzzywuzzy`     | Fuzzy string matching for TM lookups                  |

### Python Packages (Optional)

AI/MT translation and spell checking are optional features. Install only the packages for the providers you intend to use.

| Package               | Provider | Purpose                                         |
| --------------------- | -------- | ----------------------------------------------- |
| `anthropic`           | Claude   | Claude API client                               |
| `google-generativeai` | Gemini   | Google Gemini API client                        |
| `openai`              | OpenAI   | OpenAI API client                               |
| `deepl`               | DeepL    | DeepL MT API client                             |
| `pyenchant`           | —        | Spell checking (gracefully disabled if missing) |

### System Dependencies

| Dependency                                                   | Purpose                                  |
| ------------------------------------------------------------ | ---------------------------------------- |
| Enchant dictionaries (e.g., `hunspell-pl`, `hunspell-en-us`) | Language dictionaries for spell checking |

### Companion Modules

| Module                                | Purpose                                                |
| ------------------------------------- | ------------------------------------------------------ |
| `sdlxliff_xliff22_converter.py`       | Converts SDL Trados SDLXLIFF files to XLIFF 2.2        |
| `xliff22_to_sdlxliff_batch_merger.py` | Merges XLIFF 2.2 translations back into SDLXLIFF files |
| `mqxliff_xliff22_converter.py`        | Converts memoQ MQXLIFF files to XLIFF 2.2              |
| `xliff22_to_mqxliff_merger.py`        | Merges XLIFF 2.2 translations back into MQXLIFF files  |

---

## Installation

```bash
pip install PyQt6 beautifulsoup4 lxml fuzzywuzzy
```

For AI/MT translation, install the client(s) for the provider(s) you want to use:

```bash
pip install anthropic                # Claude
pip install google-generativeai      # Gemini
pip install openai                   # OpenAI
pip install deepl                    # DeepL
```

For spell checking dictionaries (Debian/Ubuntu):

```bash
sudo apt install libenchant-2-2 hunspell-en-us hunspell-pl
```

---

## Configuration Files

| File                          | Purpose                                                            |
| ----------------------------- | ------------------------------------------------------------------ |
| `~/XLIFF2Editor/xconfig.json` | All settings: API keys, preferences, recent files, context history |
| `~/xliff_editor_glossary.tsv` | Default glossary (tab-delimited, UTF-8)                            |

All persistent settings are stored in a single file inside the module directory. It is created automatically on first launch. Edit it directly to add API keys.

### xconfig.json

```json
{
  "api_keys": {
    "ANTHROPIC_API_KEY": "",
    "GOOGLE_API_KEY": "",
    "OPENAI_API_KEY": "",
    "DEEPL_API_KEY": ""
  },
  "settings": {
    "font_size": 10,
    "underline_color": {"r": 57, "g": 255, "b": 20},
    "ai_provider": "Claude",
    "glossary_file": ""
  },
  "recent_files": [],
  "contexts": []
}
```

Fill in only the key(s) for the provider(s) you intend to use. `glossary_file` is optional — if empty, `~/xliff_editor_glossary.tsv` is used.

### Migration from previous versions

On first launch after upgrading, the editor automatically migrates settings from the old `~/.xliff_editor_*.json` files and API keys from `~/config.json`, then deletes the old files. `~/config.json` itself is not deleted (it may be shared with other scripts). `GEMINI_API_KEY` in the old config is imported as `GOOGLE_API_KEY`.

---

## Functionalities

### File Operations

| Feature     | Shortcut       | Description                           |
| ----------- | -------------- | ------------------------------------- |
| Open XLIFF  | `Ctrl+O`       | Open XLIFF files (.xliff, .xlf)       |
| Open Recent | Menu           | Quick access to recently opened files |
| Save XLIFF  | `Ctrl+S`       | Save changes to current file          |
| Save As     | `Ctrl+Shift+S` | Save to a new file location           |
| Close XLIFF | `Ctrl+W`       | Close current file with save prompt   |
| Exit        | `Ctrl+Q`       | Exit application                      |

### SDLXLIFF Conversion (File → SDLXLIFF)

| Feature              | Description                                                    |
| -------------------- | -------------------------------------------------------------- |
| Import from SDLXLIFF | Convert one or more SDLXLIFF files to XLIFF 2.2 format         |
| Export to SDLXLIFF   | Merge XLIFF 2.2 translations back into original SDLXLIFF files |

### memoQ Conversion (File → memoQ)

| Feature                     | Description                                                   |
| --------------------------- | ------------------------------------------------------------- |
| Import from memoQ (MQXLIFF) | Convert one or more MQXLIFF files to XLIFF 2.2 format         |
| Export to memoQ (MQXLIFF)   | Merge XLIFF 2.2 translations back into original MQXLIFF files |

The memoQ converter handles XLIFF 1.2 files with the `MQXliff` namespace extension as exported by memoQ. Inline tags (`bpt`/`ept` flat pairs, `g`, `ph`, `x`) are converted to XLIFF 2.2 `pc`/`ph` elements for editing and converted back on export. The `mq:status` attribute is mapped to/from XLIFF 2.2 `state` using the values defined in `MQXliffSchema-4-0-21.xsd`.

### Translation Memory (TMX)

| Feature              | Shortcut     | Description                                            |
| -------------------- | ------------ | ------------------------------------------------------ |
| Load TMX             | `Ctrl+T`     | Load a TMX file for fuzzy matching                     |
| TM Matching          | Automatic    | Displays matches ≥ 70% similarity in the right panel   |
| Insert TM Match      | Double-click | Overwrites target with the selected TM match           |
| Insert Glossary Term | Single-click | Inserts the translation at cursor (does not overwrite) |

The right panel shows two sections when a segment is selected:

1. **TM matches** — sorted by score descending, format `85% — translation`. Double-clicking a match overwrites the entire target.
2. **Glossary matches** — terms from the loaded glossary file that appear in the source segment, format `source term — translation`. Single-clicking inserts the translation at the current cursor position in the target editor. If the editor is not focused, the translation is appended to the existing target text.

A greyed-out `── glossary ──` separator divides the two sections when both are present.

**TMX loading** uses `lxml.etree.iterparse` — the file is streamed element by element and each parsed node is discarded immediately after use, keeping memory consumption flat at approximately 1× the file size regardless of how large the TMX is.

### Editing

| Feature                     | Shortcut       | Description                                   |
| --------------------------- | -------------- | --------------------------------------------- |
| Insert Next Tag             | `Ctrl+N`       | Insert the next missing tag from source       |
| Clear Current Target        | `Ctrl+D`       | Clear target text of selected segment         |
| Clear All Targets           | `Ctrl+Shift+D` | Clear all target segments (with confirmation) |
| Set Status to Translated    | `Ctrl+E`       | Mark current segment as translated            |
| Copy Source to Target       | `Alt+S`        | Copy source text to target for current row    |
| Copy All Sources to Targets | `Ctrl+Shift+C` | Copy all source texts to targets              |

### Language Management

| Feature             | Shortcut       | Description                                |
| ------------------- | -------------- | ------------------------------------------ |
| Set Target Language | `Ctrl+L`       | Set or change target language code         |
| Edit Languages      | `Ctrl+Shift+L` | Edit both source and target language codes |

### AI / MT Translation

| Feature                  | Shortcut       | Description                                          |
| ------------------------ | -------------- | ---------------------------------------------------- |
| AI Translate Current     | `Ctrl+Shift+A` | Translate current segment with the selected provider |
| AI Translate All Initial | `Ctrl+Shift+T` | Batch translate all untranslated segments            |

The **AI toolbar** at the top of the window contains two controls:

- **AI selector** — choose the active provider (saved between sessions)
- **Context field** — optional free-text context injected into every prompt (editable combo box with history; expands to fill remaining toolbar width)

| Provider | Key in `xconfig.json` | Model used               |
| -------- | --------------------- | ------------------------ |
| Claude   | `ANTHROPIC_API_KEY`   | claude-sonnet-4-20250514 |
| Gemini   | `GOOGLE_API_KEY`      | gemini-2.0-flash         |
| OpenAI   | `OPENAI_API_KEY`      | gpt-4o-mini              |
| DeepL    | `DEEPL_API_KEY`       | DeepL MT                 |

**Rate limiting:** all providers are throttled to a maximum of one API call per second.

**Completion dialog:** shown after batch translation only; single-segment translation gives no dialog.

**Glossary:** loaded from a tab-delimited file (`source term TAB target term`, one pair per line, UTF-8). Only terms that actually appear in the source segment are included in the prompt — this prevents the model from reproducing the entire glossary instead of translating. Switch the glossary file at runtime via **Options → Load Glossary…**

**Context history:** each context string used for translation is saved to `xconfig.json`. Reselect previous contexts from the toolbar dropdown without retyping.

**DeepL note:** tags (`<1>`, `</1>`, `<2/>`) are temporarily renamed to valid XML names before sending to the DeepL API and restored afterwards. DeepL does not use the glossary file.

**DeepL language codes:** most target languages use the 2-letter code (`PL`, `DE`…). English and Portuguese require a regional variant (`EN-US`, `EN-GB`, `PT-BR`, `PT-PT`) and are converted automatically from the XLIFF `trgLang` attribute.

### UI Customization

| Feature                            | Description                                                            |
| ---------------------------------- | ---------------------------------------------------------------------- |
| Change Font Size                   | Adjust font size (6–24pt)                                              |
| Change Spell Check Underline Color | Customize the color of spell check underlines (dark mode only)         |
| Load Glossary…                     | Switch the active glossary TSV file at runtime                         |
| Switch to Light/Dark Theme         | Toggle between light and dark theme; system theme is applied on launch |

### Spell Checking

- Automatic spell checking for target segments
- Wavy underline for misspelled words (configurable color)
- Right-click context menu with spelling suggestions
- Add words to personal dictionary
- Supports multiple languages via enchant dictionaries

### Tag Protection

The custom editor (`TagProtectedTextEdit`) provides:

- Visual highlighting of tags in red bold text
- Protection against accidental tag modification
- Tags displayed as simplified tokens: `<1>`, `</1>`, `<1/>`
- Cursor navigation around protected tag regions

### Segment Locking

- Locked segments (`translate="no"`) are displayed with a 🔒 padlock icon
- Locked segments cannot be edited
- Grey text and darker background indicate locked status

---

## UI Layout

```
+-------------------------------------------------------------------+
| Menu Bar: File | Tasks | Options                                   |
+-------------------------------------------------------------------+
| AI: [Claude ▼]  Context: [context text...               ▼]        |
+-------------------------------------------------------------------+
| ID  | 📄 | Source              | Target         | Status | Matches|
|-----+----+---------------------+----------------+--------|--------|
| 1   | 📄 | Source text here    | Translation    | initial| 85% —… |
| 2   | 📄 | Another segment...  | ...            | transl.| stud —…|
+-------------------------------------------------------------------+
```

- **AI selector** — choose provider; persisted between sessions
- **Context field** — free-text context appended to every translation prompt; previous values available in the dropdown
- **ID** — segment identifier from the XLIFF file; 🔒 prefix for locked segments
- **📄** — file column; hover to see the full file ID in a tooltip
- **Source** — read-only source text with inline tag highlighting
- **Target** — editable target text with tag protection and spell checking
- **Status** — XLIFF `state` attribute value
- **Right panel** — TM matches (double-click to overwrite) followed by glossary matches (single-click to insert at cursor)

---

## Supported File Formats

### Input/Output

- **XLIFF 2.0, 2.1, 2.2** (.xliff, .xlf) — native format
- **TMX** (.tmx) — translation memory (read-only)

### Via Converter Modules

- **SDLXLIFF** (.sdlxliff) — SDL Trados format (import/export)
- **MQXLIFF** (.mqxliff) — memoQ format (import/export)

---

## Classes Overview

| Class                  | Purpose                                                         |
| ---------------------- | --------------------------------------------------------------- |
| `TagProtectedTextEdit` | Custom QPlainTextEdit with tag protection and spell checking    |
| `RichTextDelegate`     | Qt delegate for rendering tags in red within table cells        |
| `TMXLoadThread`        | Background thread for loading TMX files                         |
| `XLIFFLoadThread`      | Background thread for loading XLIFF files                       |
| `AITranslationThread`  | Background thread for AI translation operations                 |
| `XLIFFEditor`          | Main application window and controller (`XLIFF2Editor` package) |

---

## Status Value Mappings

### SDLXLIFF → XLIFF 2.2

| SDL Status          | XLIFF 2.2 State          |
| ------------------- | ------------------------ |
| Draft               | initial                  |
| Translated          | translated               |
| ApprovedTranslation | translated               |
| ApprovedSignOff     | final                    |
| RejectedTranslation | needs-review-translation |
| RejectedSignOff     | needs-review-translation |

### XLIFF 2.2 → SDLXLIFF

| XLIFF 2.2 State | SDL Status          |
| --------------- | ------------------- |
| initial         | Draft               |
| translated      | Translated          |
| reviewed        | ApprovedTranslation |
| final           | ApprovedSignOff     |
| needs-review-*  | RejectedTranslation |

### memoQ → XLIFF 2.2

| memoQ status             | XLIFF 2.2 state |
| ------------------------ | --------------- |
| NotStarted               | initial         |
| PreTranslated            | translated      |
| PartiallyEdited          | translated      |
| ManuallyConfirmed        | final           |
| AssembledFromFragments   | translated      |
| AutoJoined               | translated      |
| AutoSplit                | initial         |
| AutoSplitAndEmpty        | initial         |
| Ackknowledged *(schema)* | reviewed        |

### XLIFF 2.2 → memoQ

| XLIFF 2.2 state | memoQ status      |
| --------------- | ----------------- |
| initial         | NotStarted        |
| translated      | PartiallyEdited   |
| reviewed        | Ackknowledged     |
| final           | ManuallyConfirmed |
| needs-review-*  | PartiallyEdited   |

---

## Converter Module: sdlxliff_xliff22_converter.py

Converts SDLXLIFF (SDL Trados) files to XLIFF 2.2 format.

```bash
python sdlxliff_xliff22_converter.py input.sdlxliff -o output.xlf
python sdlxliff_xliff22_converter.py *.sdlxliff -o merged.xlf
```

### Using the converter from your own script

Import directly from the `XLIFF2Editor` package:

```python
from XLIFF2Editor.sdlxliff_xliff22_converter import convert_sdlxliff_to_xliff22
from pathlib import Path

# Convert a single file
stats = convert_sdlxliff_to_xliff22(
    input_paths=["project.sdlxliff"],
    output_path="project.xlf",
)
print(f"Converted {stats['total_segments']} segments from {stats['total_files']} file(s).")

# Merge an entire job package into one XLIFF for batch translation
sdlxliff_files = sorted(Path("job/").glob("*.sdlxliff"))
stats = convert_sdlxliff_to_xliff22(
    input_paths=sdlxliff_files,
    output_path="job/merged.xlf",
    verbose=False,  # suppress progress output
)
```

The function returns a dict with at least `total_segments` and `total_files`. Set `verbose=False` to suppress console output when calling from a pipeline.

## Converter Module: xliff22_to_sdlxliff_batch_merger.py

Merges XLIFF 2.2 translations back into original SDLXLIFF files.

```bash
python xliff22_to_sdlxliff_batch_merger.py merged.xlf \
    --sdlxliff-dir ./originals \
    --output-dir ./updated
```

---

## Converter Module: mqxliff_xliff22_converter.py

Converts memoQ MQXLIFF (XLIFF 1.2 + `MQXliff` namespace) files to XLIFF 2.2 format.

```bash
python mqxliff_xliff22_converter.py input.mqxliff -o output.xlf
python mqxliff_xliff22_converter.py *.mqxliff -o merged.xlf
```

### Using the converter from your own script

```python
from XLIFF2Editor.mqxliff_xliff22_converter import convert_mqxliff_to_xliff22
from pathlib import Path

stats = convert_mqxliff_to_xliff22(
    input_paths=["project.mqxliff"],
    output_path="project.xlf",
)
print(f"Converted {stats['total_segments']} segments from {stats['total_files']} file(s).")
```

### Inline tag handling

memoQ uses `bpt`/`ept` as flat siblings (not nested) to mark paired codes such as bold or italic. The converter collects the tail text of `bpt` and all content until the matching `ept` and wraps it in an XLIFF 2.2 `pc` element. `g` elements are converted to `pc` directly; `ph`, `x`, and `it` become `ph`. On export back to MQXLIFF, `pc` is written as `g` and `ph` as `x`.

---

## Converter Module: xliff22_to_mqxliff_merger.py

Merges XLIFF 2.2 translations back into original MQXLIFF files.

```bash
python xliff22_to_mqxliff_merger.py merged.xlf \
    --mqxliff-dir ./originals \
    --output-dir ./updated
```

File matching uses exact filename lookup (the file ID in XLIFF 2.2 is set to the original MQXLIFF filename), with case-insensitive fallback. Updated files are written to `--output-dir`; originals are not modified.
