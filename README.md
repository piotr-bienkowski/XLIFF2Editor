# Xliff 2 Editor

## Overview

A PyQt6-based graphical XLIFF editor for professional translation workflows. Supports XLIFF 2.0, 2.1, and 2.2 files. Provides tag-aware editing, AI/MT translation via multiple providers (Claude, Gemini, OpenAI, DeepL), translation memory (TMX) support, spell checking, SDL Trados SDLXLIFF conversion, memoQ MQXLIFF conversion, Phrase (Memsource) MXLIFF conversion, Wordfast Pro TXLF conversion, SRT-tab subtitle conversion, bilingual Excel import/export, and automatic light/dark theme switching.

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

AI/MT translation, spell checking, and Excel import/export are optional features. Install only the packages for the functionality you intend to use.

| Package               | Provider/Feature | Purpose                                                               |
| --------------------- | ---------------- | --------------------------------------------------------------------- |
| `anthropic`           | Claude           | Claude API client                                                     |
| `google-generativeai` | Gemini           | Google Gemini API client                                              |
| `openai`              | OpenAI           | OpenAI API client                                                     |
| `deepl`               | DeepL            | DeepL MT API client                                                   |
| `pyenchant`           | —                | Spell checking (gracefully disabled if missing)                       |
| `openpyxl`            | Excel            | Read/write Excel workbooks (.xlsx)                                    |
| `regex`               | Excel            | Unicode-aware SRX segmentation (falls back to stdlib `re` if missing) |

`openai` does double duty: it is the OpenAI MT provider *and* the client the HybridTM batch review uses to reach OpenRouter, so the review needs it even if you never translate with OpenAI.

All of the above are listed in `requirements.txt`:

```bash
pip install -r requirements.txt
```

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
| `mxliff_xliff22_converter.py`         | Converts Phrase (Memsource) MXLIFF files to XLIFF 2.2  |
| `xliff22_to_mxliff_merger.py`         | Merges XLIFF 2.2 translations back into an MXLIFF file |
| `excel_xliff22_converter.py`          | Converts bilingual Excel workbooks to XLIFF 2.2        |
| `xliff22_to_excel_merger.py`          | Merges XLIFF 2.2 translations back into Excel          |
| `txlf_xliff22_converter.py`           | Converts Wordfast Pro TXLF files to XLIFF 2.2          |
| `xliff22_to_txlf_merger.py`           | Merges XLIFF 2.2 translations back into TXLF files     |
| `srt_xliff22_converter.py`            | Converts SRT-tab subtitle files to XLIFF 2.2           |
| `xliff22_to_srt_merger.py`            | Merges XLIFF 2.2 translations back to SRT-tab          |
| `hybridtm_client.py`                  | Client for a local HybridTM semantic+fuzzy TM server   |
| `tm_review.py`                        | HybridTM match tiering, review prompt, reply guards    |
| `tm_review_ui.py`                     | Review dialogs and background threads                  |
| `srx_segmenter.py`                    | SRX 2.0 sentence segmenter (used by Excel converter)   |
| `segment.srx`                         | SRX 2.0 segmentation rules                             |

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

For Excel import/export:

```bash
pip install openpyxl regex
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

### Wordfast Pro Conversion (File → Wordfast Pro)

| Feature           | Description                                                  |
| ----------------- | ------------------------------------------------------------ |
| Import from TXLF  | Convert one or more TXLF files to XLIFF 2.2 format           |
| Export to TXLF    | Merge XLIFF 2.2 translations back into the original TXLF files |

Like the SDLXLIFF and memoQ filters this is a directory-paired merge: you are asked for the folder holding the original TXLF files and an output folder, and files are matched by name.

### SRT-tab Conversion (File → SRT)

| Feature               | Description                                              |
| --------------------- | -------------------------------------------------------- |
| Import from SRT-tab   | Convert a tab-separated subtitle file to XLIFF 2.2       |
| Export to SRT-tab     | Write the translations back out in the same format        |

### Phrase Conversion (File → Phrase (Memsource))

| Feature                        | Description                                                  |
| ------------------------------ | ------------------------------------------------------------ |
| Import from Phrase (MXLIFF)    | Convert one or more MXLIFF files to XLIFF 2.2 format         |
| Export to Phrase (MXLIFF)      | Merge XLIFF 2.2 translations back into the original MXLIFF   |

Unlike the other formats, the export is a single-file merge: a joined Phrase job keeps every file inside one `.mxliff`, so you are asked for the original `.mxliff` and an output path rather than two directories. Keep the file downloaded from Phrase — it is required to export.

### Bilingual Excel Conversion (File → Excel)

| Feature           | Description                                                             |
| ----------------- | ----------------------------------------------------------------------- |
| Import from Excel | Convert a bilingual Excel workbook (.xlsx) to XLIFF 2.2 for editing     |
| Export to Excel   | Merge XLIFF 2.2 translations back into the original Excel file in-place |

An **Import dialog** lets you specify:

| Setting         | Default | Description                                                                     |
| --------------- | ------- | ------------------------------------------------------------------------------- |
| Source language | `en-US` | BCP-47 language tag for the source column                                       |
| Target language | `pl-PL` | BCP-47 language tag for the target column                                       |
| Source column   | `A`     | Excel column letter(s) containing source text                                   |
| Target column   | `B`     | Excel column letter(s) where translations will be merged                        |
| First data row  | `2`     | First row number containing translatable content (skips header rows)            |
| Segment source  | off     | When checked, splits source cells into sentence-level units using SRX 2.0 rules |

After import, the XLIFF is offered for saving under the original filename with a `.xlf` extension.

**Round-trip metadata** is stored in the XLIFF so the merger knows where to write each translation back:

- `x-excel-row` on each `<unit>` — the 1-based Excel row number the segment came from
- `x-excel-src-col` / `x-excel-tgt-col` on `<file>` — the source and target column letters

**Segmentation** (`Segment source` checkbox):

When segmentation is enabled, long source cells are split into sentence-level `<unit>` elements using SRX 2.0 rules (`segment.srx`). Multiple units from the same cell share the same `x-excel-row` and are joined back on export. Alt+Enter line breaks (`\n`) within a cell are handled separately from SRX rules:

- `\n` followed by an uppercase letter is treated as a segment boundary regardless of punctuation.
- `\n` followed by a lowercase letter (a typographic line wrap within a sentence) is preserved as an inline `<ph equiv="\n"/>` tag.

On **export**, the merger reconstructs the original cell structure: segments are joined with a space for SRX-based boundaries and with `\n` for Alt+Enter boundaries. Inline `<ph equiv="\n"/>` tags in translated segments are converted back to `\n` characters in the Excel cell.

The memoQ converter handles XLIFF 1.2 files with the `MQXliff` namespace extension as exported by memoQ. Inline tags (`bpt`/`ept` flat pairs, `g`, `ph`, `x`) are converted to XLIFF 2.2 `pc`/`ph` elements for editing and converted back on export. The `mq:status` attribute is mapped to/from XLIFF 2.2 `state` using the values defined in `MQXliffSchema-4-0-21.xsd`.

### Leverage from another XLIFF (Tasks → Leverage from Xliff…)

Pre-fills untranslated segments from a previous bilingual file — an earlier version of the same job, or a sibling deliverable. Accepts SDLXLIFF and XLIFF 2.x, and asks for a minimum fuzzy threshold (default 70%).

Only unlocked, untranslated segments are touched. Matching is on tag-stripped source text, so formatting differences do not prevent a hit.

**Tags are transferred only on exact matches**, and only when the current source and the leverage source have the same tag count and the same paired/unpaired pattern; the target is then rebuilt using the current segment's own tag numbering. Every other insertion — an exact match whose tag signature differs, and every fuzzy match — goes in as plain text, rather than producing a segment whose tags do not match its source.

The completion dialog breaks the run down accordingly: exact matches with tags transferred, exact matches that fell back to plain text, fuzzy matches at or above the threshold, and segments skipped as locked or already translated.

### HybridTM Semantic Translation Memory

[HybridTM](https://github.com/maxprograms-com/HybridTM) is a local semantic + fuzzy TM engine. Point the editor at an instance by setting `hybridtm_instance` under `settings` in `xconfig.json` (or in the review dialog, which saves it).

**Side panel.** With an instance configured, selecting a row also queries HybridTM and appends its hits below the loaded-TMX fuzzy matches under a `── HybridTM ──` separator, labelled `fuzzy% / sem%`. The lookup runs on a background thread, so row selection never blocks on it, and a slow result for a row you have already left is discarded. Double-click inserts, exactly as for a TMX hit.

**Batch review** (Tasks → HybridTM Batch Review…). Reviews existing translations rather than creating them: each segment's source is looked up in HybridTM, the matches are tiered, and an LLM judges whether the current target should change. Scope is unconfirmed segments, all translated segments, or the visible rows; segments locked in the source tool are skipped by default. **100%, 101% and context (CM) matches are never reviewed, confirmed or not** — they came out of the TM unchanged, so judging them against that same TM only re-litigates the TM's own content. Both importers' conventions are recognised (Phrase writes `m:score` 1.01 for its 101% context match; SDL writes percent 100 with a *Context Match* system). On the ABB job this takes the review from 3794 segments to 692. **Nothing is modified until you apply it** — results open in a triage table where each suggested fix has a checkbox.

In that table the **Suggestion column is editable**: correct a proposal before applying it, or type your own fix into a `CHECK` row, which makes that row applicable. Clearing a suggestion un-ticks it again. Every other column is read-only but selectable, and **Ctrl+C** copies the selected cells as tab-separated text, so source and target can be lifted out into a note or a query.

#### Crash safety and resuming

A review is billed per segment and can run for an hour, so progress is written to `~/.cache/xliff2editor/reviews/<file>.review.json` as it goes — atomically, via a temporary file, so an interrupted write cannot truncate the last good copy. `REVIEW_SAVE_EVERY` in `Xedaibt.py` sets the flush interval (default 5 segments), which bounds what a crash can destroy.

**Clean verdicts are saved as well as flagged ones.** That is what makes a resume worth having: without them a restart would re-review — and re-pay for — every segment it had already judged. Start a review of the same file again and the editor offers two things:

- **reopen** the saved results and go straight to the triage dialog, or
- **resume**, skipping the segments already judged and reviewing only what is left.

The file is deleted only once fixes have actually been applied, so a run also survives a cancel or the dialog being closed by mistake.

The model is reached through OpenRouter, using `OPENROUTER_API_KEY` from `~/config.json`. The model id is `hybridtm_model` in `xconfig.json`; the default and its settings come from `~/gls_openrouter_review.py`:

| Setting | Value | Why |
| --- | --- | --- |
| `DEFAULT_MODEL` | `google/gemini-2.5-pro` | $1.25/$10 per M, and unlike the 3.1 Pro line it honours a reduced reasoning budget |
| `MODEL_FLOOR_SUFFIX` | `:floor` | sorts providers by price instead of load-balancing across them |
| `REASONING_BUDGET` | 128 | reasoning is **mandatory** on Gemini Pro (`enabled:false` → HTTP 400) and is billed at the output rate, so it dominates the bill |
| `REASONING_EFFORT` | `low` | fallback when `REASONING_BUDGET` is `None` |
| `MAX_TOKENS` / cap | 8192 / 32768 | a ceiling, not a charge; doubled on `finish_reason == "length"` |
| `MIN_DELAY` | 1.5 s | between calls |

An effort *level* is a fraction of `max_tokens` and therefore drifts whenever `MAX_TOKENS` changes, which is why an absolute `REASONING_BUDGET` is pinned instead. Note that a reasoning cap does **not** trip `finish_reason == "length"`, so too small a budget degrades quietly — the suggestion guards are the backstop.

#### Token saving

| Lever | Effect on the ABB job |
| --- | --- |
| Skip 100/101/CM matches | 3794 → 692 segments |
| Repeat cache on source+target | 692 → 589 calls (15% saved); also 103 fewer HybridTM lookups |
| Glossary filtered to the job's sources | only terms that actually occur are sent |
| Stable system prompt | built once per run so OpenRouter can cache the prefix |
| `REASONING_BUDGET = 128` | measured 3.1× cheaper than 512 ($0.0096 vs $0.0297 over six segments) |

Measured at budget 128: ~$0.0015 per call, ~414–487 input tokens per call, reasoning 53–60% of output. A full pass over the 692 in-scope ABB segments is therefore roughly **$0.85–0.95**.

The end-of-run summary reports calls, repeat-cache hits, tokens in/out, reasoning tokens, cached prompt tokens and reported cost. On this job `Cached prompt tokens` reads 0 and the summary says so — the system prompt here is only a few hundred tokens, well under the prefix length Gemini requires before implicit caching engages. That is expected, not a fault; caching pays off for the large job-specific prompts the standalone scripts use.

Raising `REASONING_BUDGET` changes marginal judgement but not the substantive catches. Measured over six segments, 128 and 512 agreed on every clear case (a wrong number, a TM terminology clash) and differed only on two borderline stylistic calls — in opposite directions.

#### Setting up HybridTM

The server is a Node package, not a Python one, so it is not covered by `requirements.txt`. It needs **Node 24+ / npm 11+**.

```bash
# Install locally, in your home directory. Never -g: a global copy shadows the
# local one and the two drift apart.
cd ~ && npm install hybridtm

# Create an instance. "large" is onnx-community/gte-multilingual-base (768d);
# "compact" and "standard" are smaller and faster but score noticeably worse
# across languages. The model downloads on first use into ~/.cache/hybridtm.
~/node_modules/.bin/hybridtm create -name myjob \
    -path ~/hybridtm/myjob.lancedb -model large

# Populate it from a TMX, XLIFF or SDLTM
~/node_modules/.bin/hybridtm import -name myjob -file ~/TMX/myjob.tmx

# Check it registered
~/node_modules/.bin/hybridtm list
```

Then set `hybridtm_instance` to `myjob` in `xconfig.json`, or pick it from the review dialog, which saves it for you. The editor starts `hybridtm serve` on 127.0.0.1:8050 by itself when it needs it.

Three things that will bite you otherwise:

- **Stop the server before a CLI import.** It holds the LanceDB open. `hybridtm stop`, import, then let the editor restart it.
- **A server started *before* an instance was created cannot see it.** If `open` reports the instance does not exist, restart the server.
- **Language codes must match the TMX exactly.** `en-US` finds matches where `en` silently returns nothing — no error, just an empty result.

The batch review also needs `OPENROUTER_API_KEY` in `~/config.json` (or the environment). The side panel does not — it is pure TM lookup and costs nothing.

#### Match tiering

Thresholds were calibrated against a 32k-entry index:

| Tier | Requires | Presented to the model as |
| --- | --- | --- |
| CLOSE | fuzzy ≥ 70 (≥ 90 for sources of ≤ 3 words), max 5 | reference for terminology |
| RELATED | semantic ≥ 90 **and** fuzzy ≥ 38, max 3 | phrasing reference, explicitly do-not-copy |

Two properties of the engine drive those numbers. HybridTM's `fuzzy` is an LCS character score that under-scores a short source contained in a longer TM entry, so the score used is the higher of it and difflib's. And the `gte` embedding rates *unrelated* sentences from the same domain at 90–98 semantic, so semantic alone can never qualify a match — hence the fuzzy floor on RELATED, and no RELATED tier at all for short sources, whose embeddings are noisy.

A match whose source and target both equal the current segment is dropped. The job's own translations are usually already in the TM, and such a match would only confirm whatever is there, mistakes included. A match whose numbers differ from the current source is passed through flagged, with an instruction never to copy numbers from it.

#### Verdicts and guards

The model returns `OK`, `FIX` (with a full corrected target) or `CHECK` (doubtful, no correction offered). Before a `FIX` is ever offered for application it must survive three checks, and is downgraded to `CHECK` otherwise:

- the suggestion carries exactly the inline tag tokens the segment had, in the same order — a suggestion that drops, adds or reorders `<1/>` would silently destroy a code;
- it introduces no number absent from both source and target, since the TM is full of near-identical sentences differing only in their figures;
- it actually differs from the current target.

An unparseable reply becomes a `CHECK` rather than being discarded, so a model failure shows up as something to look at instead of a silent pass.

Measured on 60 prose segments of a real ABB job: 17% flagged, of which the tag guard downgraded two. Expect a higher rate on short UI strings, where the model is more inclined to propose stylistic rewrites; the prompt lives in `tm_review.build_system_prompt()` if you want to tighten it.

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

### Segment Filter Bar

A filter bar sits between the AI toolbar and the segment table. It hides non-matching rows in real time without modifying the file.

| Control | Description |
| ------- | ----------- |
| **Filter source…** | Show only segments whose source text contains the entered string |
| **Filter target…** | Show only segments whose target text contains the entered string |
| **AND / OR** | When both fields are filled: AND requires both to match; OR requires either to match |
| **Regex** | Treat filter strings as regular expressions (Python `re` syntax, case-sensitive) |
| **🔍** | Apply the filter (Enter in either field also applies) |
| **✕** | Clear both fields and show all rows |

- Filtering is case-insensitive in plain-text mode and case-sensitive in Regex mode.
- Batch operations (AI Translate All, Copy All Sources to Targets, Clear All Targets) operate only on the **visible** (non-hidden) rows while a filter is active.
- The filter is cleared automatically when a file is opened or closed.

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

### Tag and XML Safety

Inline tags appear in the grid as numbered tokens — `<1/>` standalone, `<1>...</1>` paired — and everything else in the cell is literal text. Saving escapes every literal run and balances the tokens, so the written XLIFF is always well-formed:

| In the cell                             | Saved as                                      |
| --------------------------------------- | --------------------------------------------- |
| `&`, `<`, `>` in the translation        | Escaped; the characters survive verbatim      |
| A token naming a tag not in the segment | Left as literal text                          |
| `<1/>` for a paired tag (or vice versa) | Left as literal text                          |
| `<1>` with the closing `</1>` deleted   | Closed automatically                          |
| `</1>` with the opening `<1>` deleted   | Left as literal text                          |
| Crossed tokens `<1>a<2>b</1></2>`       | Re-nested to stay well-formed                 |

Tag numbering is shared across nesting, so `<pc id="1"><pc id="2">` reads as `<1><2>` and both ids are preserved. Content held inside a standalone tag (memoQ stores the original code inside `<ph>`) is kept and rewritten on save. Attribute values are quoted, so a tag carrying raw markup in an attribute cannot break the file.

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
- **TXLF** (.txlf) — Wordfast Pro format (import/export)
- **SRT-tab** (.srt, .txt) — tab-separated subtitle format (import/export)
- **MXLIFF** (.mxliff) — Phrase / Memsource format (import/export)
- **Excel** (.xlsx) — bilingual workbook format (import/export)

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

---

## Converter Module: txlf_xliff22_converter.py

Converts Wordfast Pro TXLF — XLIFF 1.2 with GS4TR extensions — to XLIFF 2.2.

```bash
python txlf_xliff22_converter.py input.txlf -o output.xlf
python txlf_xliff22_converter.py *.txlf -o merged.xlf
```

### Inline tag handling

TXLF uses five inline conventions, and unlike memoQ its paired codes are matched by `@rid` rather than `@id`:

| TXLF | Meaning | XLIFF 2.2 |
| --- | --- | --- |
| `bx` / `ex` | paired split, self-closing, matched by `@rid` | `pc` |
| `bpt` / `ept` | paired split carrying the formatting XML, matched by `@rid` | `pc` |
| `g` | paired wrapping | `pc` |
| `ph` | unpaired standalone with content | `ph` |
| `x` | unpaired self-closing | `ph` |

The converter pairs `bx`/`ex` and `bpt`/`ept` by walking siblings until the matching `@rid` is found, so a split pair becomes one `pc` wrapping everything between its halves. A `bx`/`bpt` nested inside a `g` — which should not occur, but does in the wild — degrades to a `ph` carrying the `rid` rather than being dropped.

### Status mapping

| TXLF state | XLIFF 2.2 | and back |
| --- | --- | --- |
| *(empty)*, `needs-translation`, `new` | `initial` | `needs-translation` |
| `translated` | `translated` | `translated` |
| `needs-review-translation` | `needs-review-translation` | `needs-review-translation` |
| `signed-off`, `final` | `final` | `signed-off` |

---

## Converter Module: xliff22_to_txlf_merger.py

Merges XLIFF 2.2 translations back into the original TXLF files.

```bash
python xliff22_to_txlf_merger.py merged.xlf \
    --txlf-dir ./originals \
    --output-dir ./updated
```

The original inline tag structure is not reconstructed from the XLIFF — it is **cloned from the TXLF source segment**. The merger builds a lookup of the source's own tag elements by id, then rebuilds the target by matching each XLIFF 2.2 `pc`/`ph` id against it and deep-copying the corresponding element. That keeps `bpt`/`ept` formatting payloads and `ph`/`x` attributes byte-identical, which reconstructing them from the XLIFF side could not guarantee.

Attributes on the target that are neither state nor content — `gs4tr:seginfo`, `xml:space` and the rest of the GS4TR extension namespace — are preserved. Files are matched to XLIFF `file` ids by name, with a case-insensitive fallback; originals are never modified.

---

## Converter Module: srt_xliff22_converter.py

Converts a tab-separated subtitle file to XLIFF 2.2. The expected input is one subtitle per line:

```
00:00:01,000 --> 00:00:05,000<TAB>Subtitle text here
```

Lines without a tab, and empty lines, are skipped; the file is read as `utf-8-sig` so a BOM does no harm. There is **no segmentation** — one unit per input line, because a subtitle cue should not be split.

Round-trip metadata is stored on each `unit`: `x-srt-timecode` holds the timecode string verbatim and `x-srt-line` the 1-based input line number.

```xml
<unit id="1" x-srt-timecode="00:00:01,000 --> 00:00:05,000" x-srt-line="1">
  <segment id="1"><source>Hello world.</source><target/></segment>
</unit>
```

---

## Converter Module: xliff22_to_srt_merger.py

Writes the translations back out in the same tab-separated format, ordered by `x-srt-line` so document order is guaranteed regardless of how the units sit in the file.

A unit with an empty target falls back to its **source** text rather than being skipped, so the output line count always matches the input and no cue is silently lost. Export refuses to run at all on an XLIFF that has no `x-srt-timecode` anywhere — that file did not come from an SRT import and there would be no timecodes to write.

---

## Converter Module: mxliff_xliff22_converter.py

Converts Phrase (Memsource) MXLIFF — XLIFF 1.2 carrying the `http://www.memsource.com/mxlf/2.0` namespace — to XLIFF 2.2.

```bash
python mxliff_xliff22_converter.py job.mxliff -o job.xlf
python mxliff_xliff22_converter.py *.mxliff -o merged.xlf --skip-locked
```

### What makes MXLIFF different

**Inline codes live in the text, not in elements.** There are no `bpt`/`ept`/`ph`/`x`/`g` elements inside `source` and `target`. Phrase writes codes into the text itself in brace notation:

| Notation      | Meaning                                                     |
| ------------- | ----------------------------------------------------------- |
| `{1}`         | Standalone code                                             |
| `{1>text<1}`  | Paired code with content, numeric id                        |
| `{b>text<b}`  | Paired intrinsic formatting code, letter id (`b`, `B`, `i`) |

Numeric ids reference `m:mark` entries in `m:tunit-metadata`; letter ids are intrinsic and have no metadata entry. Paired codes nest (three deep in observed files). The converter parses this notation into flat XLIFF 2.2 `sc`/`ec`/`ph` elements rather than nested `pc`, because Phrase's own model is flat: `{1>` and `<1}` are independent markers referencing mark id 1, and the notation permits sequences that do not nest cleanly. Keeping them flat makes the round-trip exact. Text that merely looks like the notation (`cost {approx} 5`, a bare `{`) is left verbatim.

Only a mark's short `m:type` is copied onto the generated element. Its `m:content` — the original DOCX/DITA markup, often hundreds of characters and containing quotes — is deliberately left in the `.mxliff`, which the merger reads directly.

**Joined jobs.** One `.mxliff` may hold many `file` elements, each with its own `body`. `group` ids restart at 0 in every file and therefore collide across the document, so they must never be used for matching; `trans-unit` ids carry the job's `m:task-id` prefix and are unique document-wide. Each internal file becomes its own XLIFF 2.2 `file` element, and duplicate `original` names are disambiguated with the task id.

**Attribute order varies by Phrase version** (`m:version` 2.13 through 2.17 observed), so the file must be read with an XML parser, never by pattern matching.

### Status and match mapping

| MXLIFF                        | XLIFF 2.2                            |
| ----------------------------- | ------------------------------------ |
| `m:confirmed="1"`             | `state="final"`                      |
| `m:confirmed="0"`, has target | `state="translated"`                 |
| `m:confirmed="0"`, no target  | `state="initial"`                    |
| `m:locked="true"`             | `translate="no"` (padlock in grid)   |
| `m:score="1.01"`              | `match="CM"` (101% context match)    |
| `m:score="0.87"`, origin `tm` | `match="87%"`                        |
| `m:trans-origin="mt"`         | `match="MT"`                         |

Each unit is tagged `x-mxliff-origin="phrase"`, which the export guard and the merger key off; `x-mxliff-group` and `x-mxliff-para-id` keep the Phrase provenance visible.

---

## Converter Module: xliff22_to_mxliff_merger.py

Merges XLIFF 2.2 translations back into the original MXLIFF so it can be re-uploaded to Phrase as a bilingual MXLIFF.

```bash
python xliff22_to_mxliff_merger.py translated.xlf \
    --mxliff original.mxliff \
    -o updated.mxliff
```

This is a single-file merge keyed on `trans-unit` id, not the directory pairing the SDLXLIFF/MQXLIFF/TXLF mergers use, because a joined job is already one file.

Everything outside `target`, `m:confirmed` and `m:level-edited` is left byte-identical, including the CDATA in-context preview skeleton in the header and the `m:extra` user list. `m:tunit-target-metadata` is left untouched: Phrase treats it as a verbatim copy of `m:tunit-metadata` — across every sample examined it retains marks the target dropped and keeps source order even when the target reorders them — so filtering it to the target's own codes would diverge from what Phrase itself writes.

Segments locked in Phrase are skipped by default (`--include-locked` to override). Segments whose target text actually changed get `m:level-edited="true"` (`--no-mark-edited` to suppress).

---

## Converter Module: excel_xliff22_converter.py

Converts a bilingual Excel workbook (.xlsx) to XLIFF 2.2. Can be used standalone or via the **File → Excel → Import from Excel** menu.

### Using the converter from your own script

```python
from XLIFF2Editor.excel_xliff22_converter import convert_excel_to_xliff22

stats = convert_excel_to_xliff22(
    input_path="brochure.xlsx",
    output_path="brochure.xlf",
    src_lang="en-US",
    tgt_lang="pl-PL",
    src_col="A",        # column letter(s) for source text
    tgt_col="B",        # column letter(s) for target text
    first_row=2,        # first data row (skip header)
    segment=True,       # split cells into sentence-level units
    srx_path=None,      # defaults to segment.srx next to this file
)
print(f"Converted {stats['total_rows']} rows into {stats['total_units']} units.")
```

### Newline handling

Excel cells often contain Alt+Enter (`\n`) line breaks. The converter handles them in two ways:

- **`\n` before an uppercase letter** — treated as a segment boundary. The text is pre-split at this point before SRX rules are applied. The boundary is marked with a trailing `<ph equiv="\n"/>` on the last sentence of the preceding block.
- **`\n` before a lowercase letter** — a typographic line wrap within a sentence. Preserved as an inline `<ph equiv="\n"/>` in the `<source>` element.

This ensures that cells like `"Sentence one.\nBecause of this."` and `"Title line\ncontinued in lower case"` are handled correctly on both import and export.

---

## Converter Module: xliff22_to_excel_merger.py

Merges XLIFF 2.2 translations back into the original Excel workbook in-place (target column only).

### Using the merger from your own script

```python
from XLIFF2Editor.xliff22_to_excel_merger import merge_xliff22_to_excel

result = merge_xliff22_to_excel(
    xliff_path="brochure.xlf",
    excel_path="brochure.xlsx",   # modified in-place
)
print(f"Written {result['rows_written']} row(s), skipped {result['units_skipped']}.")
```

The merger reads `x-excel-tgt-col` from the XLIFF `<file>` element to determine which Excel column to write to, so the correct column is always used regardless of what was entered in the import dialog. It raises `ValueError` if the XLIFF was not produced by `convert_excel_to_xliff22`.

### Newline reconstruction

Segment boundaries that originated from Alt+Enter line breaks are identified by a trailing `<ph>` on the source element (empty tail, any `equiv` value — translation tools may change `equiv="\n"` to a space). Such boundaries are joined with `\n` in the merged cell; SRX-based sentence boundaries are joined with a space. Trailing `<ph>` tags are stripped from the target text before writing. Inline `<ph equiv="\n"/>` tags within a target are converted back to `\n`.
