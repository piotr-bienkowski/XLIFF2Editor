"""
SRX 2.0 sentence segmenter.

Parses segment.srx once at construction; segment() is fast and thread-safe.
Uses the `regex` module for Unicode property support (\\p{Lu} etc.);
falls back to stdlib `re` if not installed (loses Unicode properties).
"""

from __future__ import annotations

from pathlib import Path

try:
    import regex as re_module
except ImportError:
    import re as re_module  # type: ignore[no-redef]

from lxml import etree

SRX_NS = 'http://www.lisa.org/srx20'


def _safe_compile(pattern: str):
    """Compile pattern; return None on error."""
    if not pattern:
        return None
    try:
        return re_module.compile(pattern)
    except Exception:
        return None


def _safe_compile_end(pattern: str):
    """Compile pattern anchored to end of string."""
    if not pattern:
        return None
    try:
        return re_module.compile(f'(?:{pattern})$')
    except Exception:
        return None


class SrxSegmenter:
    """
    Parse an SRX file and segment text into sentences.

    Usage:
        segmenter = SrxSegmenter()          # uses segment.srx next to this file
        sentences = segmenter.segment(text, 'en-US')

    Limitations:
    - Always uses cascade=yes semantics (all matching language maps contribute rules).
      SRX files with cascade="no" will silently produce incorrect results.
    - Java-only regex flags (e.g. (?U)) cause those rules to be silently dropped.
      This affects Russian/Ukrainian/Belarusian in segment.srx but not EN/PL.
    """

    def __init__(self, srx_path=None):
        if srx_path is None:
            srx_path = Path(__file__).parent / 'segment.srx'
        # _rules: rulename → [(is_break, b_re, a_re, b_end_re), ...]
        self._rules: dict[str, list] = {}
        # _maps: [(lang_fullmatch_re, rulename), ...]
        self._maps: list = []
        self._parse(Path(srx_path))

    # ── parsing ──────────────────────────────────────────────────────────────

    def _parse(self, path: Path) -> None:
        tree = etree.parse(str(path))
        root = tree.getroot()
        ns = SRX_NS

        for lr in root.findall(f'.//{{{ns}}}languagerule'):
            name = lr.get('languagerulename', '')
            rules = []
            for rule in lr.findall(f'{{{ns}}}rule'):
                is_break = rule.get('break', 'yes') == 'yes'
                before = rule.findtext(f'{{{ns}}}beforebreak') or ''
                after  = rule.findtext(f'{{{ns}}}afterbreak')  or ''
                b_re     = _safe_compile(before)
                a_re     = _safe_compile(after)
                b_end_re = _safe_compile_end(before)
                if b_re is not None or a_re is not None:
                    rules.append((is_break, b_re, a_re, b_end_re))
            self._rules[name] = rules

        for lm in root.findall(f'.//{{{ns}}}languagemap'):
            pattern  = lm.get('languagepattern', '')
            rulename = lm.get('languagerulename', '')
            try:
                lp_re = re_module.compile(pattern, re_module.IGNORECASE)
                self._maps.append((lp_re, rulename))
            except Exception:
                pass

    # ── public API ───────────────────────────────────────────────────────────

    def segment(self, text: str, lang: str) -> list[str]:
        """
        Split *text* into sentences using the SRX rules for *lang*.

        Returns ``[text]`` unchanged when no split is found.
        Returns ``[]`` when *text* is empty.
        """
        if not text:
            return []
        if not text.strip():
            return [text]

        rules = self._get_rules(lang)
        if not rules:
            return [text]

        break_rules   = [(b_re, a_re)
                         for (ib, b_re, a_re, _bnd) in rules if ib]
        nobreak_rules = [(b_end_re, a_re)
                         for (ib, _b, a_re, b_end_re) in rules if not ib]

        candidates = self._find_candidates(text, break_rules)
        if not candidates:
            return [text]

        real_breaks = self._filter_nobreaks(text, candidates, nobreak_rules)
        if not real_breaks:
            return [text]

        return self._split(text, real_breaks)

    # ── internals ────────────────────────────────────────────────────────────

    def _get_rules(self, lang: str) -> list:
        """Collect rules from all language maps matching *lang* (cascade)."""
        combined: list = []
        for lp_re, rulename in self._maps:
            if lp_re.fullmatch(lang):
                combined.extend(self._rules.get(rulename, []))
        return combined

    def _find_candidates(self, text: str, break_rules: list) -> set[int]:
        """Return set of candidate break positions (end of beforebreak match)."""
        candidates: set[int] = set()
        for b_re, a_re in break_rules:
            if b_re is None:
                continue
            for m in b_re.finditer(text):
                pos = m.end()
                if pos >= len(text):
                    continue
                if a_re is None or not a_re.pattern or a_re.match(text[pos:]):
                    candidates.add(pos)
        return candidates

    def _filter_nobreaks(
        self, text: str, candidates: set[int], nobreak_rules: list
    ) -> set[int]:
        """Remove candidates that are inhibited by a no-break rule."""
        real: set[int] = set()
        for pos in candidates:
            after = text[pos:]
            inhibited = False
            for b_end_re, a_re in nobreak_rules:
                if b_end_re is None:
                    continue
                if not b_end_re.search(text[:pos]):
                    continue
                if a_re is None or not a_re.pattern or a_re.match(after):
                    inhibited = True
                    break
            if not inhibited:
                real.add(pos)
        return real

    def _split(self, text: str, breaks: set[int]) -> list[str]:
        result: list[str] = []
        prev = 0
        for pos in sorted(breaks):
            seg = text[prev:pos].strip()
            if seg:
                result.append(seg)
            prev = pos
        tail = text[prev:].strip()
        if tail:
            result.append(tail)
        return result if result else [text]
