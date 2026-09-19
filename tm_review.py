#!/usr/bin/env python3
"""
HybridTM-backed batch review for XLIFF2Editor.

For each segment this gathers semantic + fuzzy matches from a HybridTM instance,
sorts them into two tiers, and asks an LLM whether the existing target is
consistent with them.  It reports a verdict and a suggested fix; it never edits
a segment on its own -- the caller decides what to apply.

The tiering thresholds and the "reference, not authority" framing are carried
over from ~/wfp_openrouter_review.py, where they were calibrated against a real
32k-entry index:

* HybridTM's own fuzzy is an LCS character score and is stricter than difflib,
  so CLOSE needs 70 -- but the score used is the higher of it and difflib,
  because HybridTM under-scores a short source contained in a longer TM entry.
* The gte embedding rates *unrelated* sentences from the same domain at 90-98
  semantic, so semantic alone can never qualify a match.  RELATED therefore
  demands both semantic >= 90 and some real textual overlap (fuzzy >= 38), and
  those matches are explicitly labelled do-not-copy.
* Embeddings of 1-3 word strings are noisy, so short sources need fuzzy 90 and
  get no RELATED tier at all.

The model is reached through OpenRouter, like the WFP script: the same key in
~/config.json, and no direct Anthropic API use.
"""

from __future__ import annotations

import difflib
import json
import os
import random
import re
import time
from pathlib import Path

DEFAULT_MODEL = 'google/gemini-2.5-pro'
# Most models are served by several providers at different rates. ":floor"
# sorts them by price; without it OpenRouter load-balances across them. Drop it
# if the cheapest provider turns slow or flaky.
MODEL_FLOOR_SUFFIX = ':floor'
OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'

# Reasoning is MANDATORY on the Gemini Pro lines -- reasoning:{enabled:false}
# returns HTTP 400 -- and it is billed at the completion rate, so it dominates
# the bill. An effort *level* is a fraction of max_tokens and therefore drifts
# whenever MAX_TOKENS changes, so an absolute ceiling is pinned instead:
# gemini-2.5-pro honours reasoning.max_tokens (unlike the 3.1 Pro line, which
# silently ignores it). Set REASONING_BUDGET to None to fall back to the effort
# level. A reasoning cap does NOT trip finish_reason == "length", so an
# under-budgeted run degrades quietly rather than erroring -- which is why the
# review validates every suggestion before offering it.
REASONING_BUDGET = 128
REASONING_EFFORT = 'low'

MAX_TOKENS = 8192            # a ceiling, not a charge; only tokens used are billed
MAX_TOKENS_CAP = 32768       # doubled up to this on finish_reason == "length"
MIN_DELAY = 1.5              # seconds between calls
REQUEST_TIMEOUT = 180.0

# Match tiering -- see the module docstring for why each number is what it is.
HTM_SEARCH_FLOOR = 55
HTM_SEARCH_LIMIT = 10
HTM_CLOSE_FUZZY = 70
HTM_CLOSE_MAX = 5
HTM_RELATED_SEMANTIC = 90
HTM_RELATED_FUZZY = 38
HTM_RELATED_MAX = 3
HTM_SHORT_WORDS = 3
HTM_SHORT_FUZZY = 90

VERDICTS = ('OK', 'FIX', 'CHECK')


# ── helpers ───────────────────────────────────────────────────────────────────

def _norm_ws(text: str) -> str:
    return ' '.join((text or '').split())


def _numbers(text: str) -> list:
    return sorted(re.findall(r'\d+', text or ''))


def load_openrouter_key(config_path=None) -> str:
    """OPENROUTER_API_KEY from ~/config.json, else the environment."""
    path = Path(config_path or (Path.home() / 'config.json'))
    if path.exists():
        try:
            key = json.loads(path.read_text(encoding='utf-8')).get('OPENROUTER_API_KEY')
            if key:
                return key
        except (json.JSONDecodeError, OSError):
            pass
    return os.getenv('OPENROUTER_API_KEY', '')


# ── match tiering ─────────────────────────────────────────────────────────────

def classify_matches(source: str, matches: list, target: str) -> tuple:
    """
    Split HybridTM matches into (close, related).

    The segment's own pair is dropped: this job's targets are usually already in
    the TM, and a match that merely echoes the segment would confirm whatever is
    there, including its mistakes.
    """
    short = len(source.split()) <= HTM_SHORT_WORDS
    close_min = HTM_SHORT_FUZZY if short else HTM_CLOSE_FUZZY
    source_norm, target_norm = _norm_ws(source), _norm_ws(target)
    source_numbers = _numbers(source)

    close, related = [], []
    for match in matches:
        if _norm_ws(match['source']) == source_norm and _norm_ws(match['target']) == target_norm:
            continue                                   # self-echo
        entry = dict(match, numbers_differ=_numbers(match['source']) != source_numbers)
        if entry['best_fuzzy'] >= close_min:
            close.append(entry)
        elif (not short
              and entry['semantic'] >= HTM_RELATED_SEMANTIC
              and entry['fuzzy'] >= HTM_RELATED_FUZZY):
            related.append(entry)

    close.sort(key=lambda m: m['best_fuzzy'], reverse=True)
    related.sort(key=lambda m: m['semantic'], reverse=True)
    return close[:HTM_CLOSE_MAX], related[:HTM_RELATED_MAX]


def build_tm_block(close: list, related: list) -> str:
    """Format the two tiers for the user message."""
    lines = []
    if close:
        lines.append('TRANSLATION MEMORY -- CLOSE MATCHES (reference, not authority):')
        for match in close:
            score = f"fuzzy {match['best_fuzzy']}%, semantic {match['semantic']}%"
            flag = ('  [NUMBERS DIFFER from the current source -- never copy '
                    'numbers from this match]' if match['numbers_differ'] else '')
            lines.append(f'[{score}] EN: "{match["source"]}" | PL: "{match["target"]}"{flag}')
    if related:
        if lines:
            lines.append('')
        lines.append('RELATED TM USAGE (different sentences with a similar meaning -- '
                     'terminology and phrasing reference only; DO NOT copy them):')
        for match in related:
            lines.append(f'[semantic {match["semantic"]}%] '
                         f'EN: "{match["source"]}" | PL: "{match["target"]}"')
    return '\n'.join(lines)


# ── prompts ───────────────────────────────────────────────────────────────────

def build_system_prompt(src_lang='en-US', tgt_lang='pl-PL', glossary_section='',
                        domain='') -> str:
    domain_line = f'\nThe content is {domain}.' if domain else ''
    glossary_block = f'\n\n{glossary_section}' if glossary_section else ''
    return f"""You are a senior reviewer of {src_lang} to {tgt_lang} technical translation, \
and a native speaker of the target language.{domain_line}

You are given a source segment, its existing translation, and matches from the \
project translation memory. Judge ONLY whether the existing translation should \
change. Reply with a single JSON object and nothing else:

{{"verdict": "OK" | "FIX" | "CHECK", "suggestion": "<full corrected target, or \
empty string when verdict is OK>", "reason": "<one short sentence>"}}

Use the verdicts as follows:
- "OK"    - the translation is correct and consistent with the TM. suggestion "".
- "FIX"   - there is a definite error you can correct: a mistranslation, a \
terminology clash with a CLOSE match, a wrong or missing number, or a clear \
grammatical fault. Put the complete corrected target in suggestion.
- "CHECK" - something looks doubtful but you cannot correct it with confidence \
(ambiguous source, TM entries disagreeing with each other, missing context). \
suggestion "".

Rules:
- The TM is reference, not authority. A CLOSE match shows how this wording was \
translated before; prefer its terminology unless it is plainly wrong here.
- RELATED matches are different sentences. Never copy them; use them only to \
see which terms this project favours.
- NEVER copy numbers, codes, measurements or identifiers from a TM match. Take \
every number from the current source.
- Existing wording that is merely a different valid phrasing is "OK". Do not \
rewrite for style, and do not flag a translation only because it differs from \
the TM.
- Inline tag placeholders look like <1/> or <1>...</1>. Keep them in suggestion \
exactly as they appear in the source, same count, same order.
- Reply with the JSON object only. No markdown fence, no commentary.{glossary_block}"""


def build_user_message(source: str, target: str, tm_block: str = '',
                       context_before: str = '', context_after: str = '') -> str:
    parts = []
    if context_before or context_after:
        parts.append('SURROUNDING SEGMENTS (context only, do not review):')
        if context_before:
            parts.append(f'  before: {context_before}')
        if context_after:
            parts.append(f'  after : {context_after}')
        parts.append('')
    if tm_block:
        parts.append(tm_block)
        parts.append('')
    parts.append(f'SOURCE:\n{source}')
    parts.append(f'\nEXISTING TRANSLATION:\n{target}')
    return '\n'.join(parts)


# ── response handling ─────────────────────────────────────────────────────────

def parse_response(text: str) -> dict:
    """
    Read the model's JSON reply defensively.

    Small models wrap JSON in fences or prepend commentary, so the first
    balanced object in the reply is used. An unreadable reply becomes a CHECK
    rather than being silently dropped.
    """
    raw = (text or '').strip()
    raw = re.sub(r'^```[^\n]*\n', '', raw)
    raw = re.sub(r'\n```\s*$', '', raw).strip()

    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.S)
        if match:
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                data = None

    if not isinstance(data, dict):
        return {'verdict': 'CHECK', 'suggestion': '',
                'reason': 'unreadable model reply', 'malformed': True}

    verdict = str(data.get('verdict', '')).strip().upper()
    if verdict not in VERDICTS:
        verdict = 'CHECK'
    suggestion = str(data.get('suggestion') or '').strip()
    if verdict == 'OK':
        suggestion = ''
    return {
        'verdict': verdict,
        'suggestion': suggestion,
        'reason': str(data.get('reason') or '').strip(),
        'malformed': False,
    }


def _tag_tokens(text: str) -> list:
    return re.findall(r'<\d+/>|</?\d+>', text or '')


def validate_suggestion(source: str, target: str, result: dict) -> dict:
    """
    Downgrade a FIX that cannot be trusted.

    A suggestion that drops or invents inline tags, or that introduces a number
    absent from the source, is turned into a CHECK: applying it would corrupt
    the segment, but the reviewer still deserves to see the flag.
    """
    if result['verdict'] != 'FIX' or not result['suggestion']:
        if result['verdict'] == 'FIX':
            result = dict(result, verdict='CHECK', suggestion='',
                          reason=result['reason'] or 'FIX with no suggestion')
        return result

    suggestion = result['suggestion']
    if _tag_tokens(suggestion) != _tag_tokens(target or source):
        expected = ' '.join(_tag_tokens(target or source)) or '(none)'
        return dict(result, verdict='CHECK', suggestion='',
                    reason=f'suggestion altered inline tags (expected {expected})')

    invented = set(_numbers(suggestion)) - set(_numbers(source)) - set(_numbers(target))
    if invented:
        return dict(result, verdict='CHECK', suggestion='',
                    reason=f'suggestion introduced number(s) not in the source: '
                           f'{", ".join(sorted(invented))}')
    if _norm_ws(suggestion) == _norm_ws(target):
        return dict(result, verdict='OK', suggestion='',
                    reason='suggestion identical to the existing target')
    return result


# ── model call ────────────────────────────────────────────────────────────────

def _term_pattern(term: str):
    """Word-boundary regex for one source-language glossary term.

    Whitespace between words is flexible (a source may hyphenate or wrap where
    the termbase does not) and a trailing plural is allowed. Deliberately
    generous: keeping a term that is not really there costs a few tokens,
    dropping one that is loses a rule the reviewer was meant to enforce.
    """
    words = [re.escape(word) for word in term.lower().split()]
    if not words:
        return None
    return re.compile(r'(?<!\w)' + r'\W+'.join(words) + r'(?:s|es)?(?!\w)')


def filter_glossary_to_sources(glossary: dict, sources) -> dict:
    """
    Keep only the glossary entries whose term actually occurs in the job.

    A full client termbase runs to thousands of terms, and embedding all of it
    in a system prompt sent on every call is what dominates the bill -- most of
    those terms never appear in the job at all. Filtering happens once against
    every source, so the resulting system prompt stays byte-identical from call
    to call and can still be cached.
    """
    if not glossary:
        return {}
    blob = ' \n '.join(sources).lower()
    kept = {}
    for term, translation in glossary.items():
        pattern = _term_pattern(term)
        if pattern and pattern.search(blob):
            kept[term] = translation
    return kept


def format_glossary(glossary: dict) -> str:
    if not glossary:
        return ''
    lines = ['GLOSSARY (these renderings are binding):']
    for source_term, target_term in glossary.items():
        lines.append(f'  "{source_term}" -> "{target_term}"')
    return '\n'.join(lines)


class Usage:
    """
    Running token, cache and cost totals for one review run.

    The system prompt is built once and reused unchanged, so OpenRouter should
    cache its prefix and bill it at a fraction of the input rate. ``cached``
    is how we find out whether that actually happened -- "should" is not
    evidence. Every field is provider-reported and may be absent, so recording
    never raises.
    """

    def __init__(self):
        self.calls = self.tokens_in = self.tokens_out = 0
        self.reasoning = self.cached = 0
        self.cost = self.discount = 0.0
        self.cache_hits = 0          # segments answered without any call at all

    def record(self, response):
        self.calls += 1
        usage = getattr(response, 'usage', None)
        if not usage:
            return
        self.tokens_in += getattr(usage, 'prompt_tokens', 0) or 0
        self.tokens_out += getattr(usage, 'completion_tokens', 0) or 0

        def _detail(holder, field):
            if holder is None:
                return 0
            value = getattr(holder, field, None)
            if value is None and isinstance(holder, dict):
                value = holder.get(field)
            return value or 0

        self.reasoning += _detail(getattr(usage, 'completion_tokens_details', None),
                                  'reasoning_tokens')
        self.cached += _detail(getattr(usage, 'prompt_tokens_details', None),
                               'cached_tokens')
        for holder, field in ((usage, 'cost'), (response, 'cache_discount')):
            value = getattr(holder, field, None)
            if isinstance(value, (int, float)):
                if field == 'cost':
                    self.cost += value
                else:
                    self.discount += value

    def summary(self) -> str:
        if not self.calls:
            return 'No model calls were made.'
        hit = (self.cached / self.tokens_in * 100) if self.tokens_in else 0.0
        reasoning_pct = (self.reasoning / self.tokens_out * 100) if self.tokens_out else 0.0
        lines = [
            f'{self.calls} model call(s); {self.cache_hits} segment(s) answered '
            f'from the repeat cache.',
            f'Tokens in / out: {self.tokens_in:,} / {self.tokens_out:,} '
            f'({self.tokens_in // max(self.calls, 1):,} in per call)',
            f'Reasoning tokens: {self.reasoning:,} ({reasoning_pct:.0f}% of output, '
            f'billed at the output rate)',
            f'Cached prompt tokens: {self.cached:,} ({hit:.0f}% of input)'
            + ('' if self.cached else '  — no caching seen; the prefix may not be stable'),
        ]
        if self.discount:
            lines.append(f'Cache discount: ${self.discount:.4f}')
        if self.cost:
            lines.append(f'Reported cost: ${self.cost:.4f}')
        return '\n'.join(lines)


class ResponseTruncated(RuntimeError):
    """The model hit max_tokens even at MAX_TOKENS_CAP; its reply is incomplete."""


def make_client(api_key: str):
    import openai
    return openai.OpenAI(base_url=OPENROUTER_BASE_URL, api_key=api_key)


def _call_once(client, system, user, model, max_tokens, usage,
               max_retries=4, base_delay=5.0):
    """One completion, with backoff on rate limits, timeouts and API errors."""
    import openai
    last_error = None
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model + MODEL_FLOOR_SUFFIX,
                messages=[{'role': 'system', 'content': system},
                          {'role': 'user', 'content': user}],
                temperature=0.0,
                max_tokens=max_tokens,
                timeout=REQUEST_TIMEOUT,
                extra_body={
                    'reasoning': ({'max_tokens': REASONING_BUDGET} if REASONING_BUDGET
                                  else {'effort': REASONING_EFFORT}),
                    'usage': {'include': True},
                },
            )
            if usage is not None:
                usage.record(response)
            choice = response.choices[0]
            return choice.message.content or '', choice.finish_reason
        except openai.RateLimitError as exc:
            last_error = exc
            if attempt == max_retries - 1:
                break
            time.sleep(base_delay * (2 ** attempt) * (0.9 + random.random() * 0.2))
        except (openai.APITimeoutError, openai.APIConnectionError) as exc:
            last_error = exc
            if attempt == max_retries - 1:
                break
            time.sleep(base_delay * (2 ** attempt))
        except openai.APIStatusError as exc:
            last_error = exc
            if attempt == max_retries - 1:
                break
            time.sleep(base_delay * (2 ** attempt))
    raise RuntimeError(f'OpenRouter call failed: {last_error}')


def call_model(client, system: str, user: str, model=DEFAULT_MODEL,
               max_tokens=MAX_TOKENS, usage=None) -> str:
    """
    One completion, retrying with a doubled ceiling if the reply was cut off.

    A reply truncated by max_tokens is unparseable JSON, so it is worth paying
    for the retry rather than reporting a malformed answer.
    """
    while True:
        text, finish_reason = _call_once(client, system, user, model, max_tokens, usage)
        if finish_reason != 'length':
            return text
        if max_tokens >= MAX_TOKENS_CAP:
            raise ResponseTruncated(f'reply still cut off at max_tokens={max_tokens}')
        max_tokens = min(max_tokens * 2, MAX_TOKENS_CAP)


def review_segment(client, source: str, target: str, matches: list,
                   system_prompt: str, model=DEFAULT_MODEL,
                   context_before='', context_after='', usage=None) -> dict:
    """Review one segment. Returns the verdict dict plus the tiers that were used."""
    close, related = classify_matches(source, matches, target)
    user = build_user_message(source, target, build_tm_block(close, related),
                              context_before, context_after)
    reply = call_model(client, system_prompt, user, model=model, usage=usage)
    result = validate_suggestion(source, target, parse_response(reply))
    result['close'] = close
    result['related'] = related
    return result
