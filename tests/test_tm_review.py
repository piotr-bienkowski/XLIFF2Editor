"""
HybridTM review engine: match tiering, reply parsing, and the guards that stop
a bad suggestion reaching a segment.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from tm_review import (
    HTM_CLOSE_FUZZY, HTM_RELATED_FUZZY, HTM_RELATED_SEMANTIC, HTM_SHORT_FUZZY,
    build_tm_block, classify_matches, parse_response, validate_suggestion,
)


def match(source, target, semantic=95, fuzzy=80, best=None):
    return {'source': source, 'target': target, 'semantic': semantic,
            'fuzzy': fuzzy, 'best_fuzzy': best if best is not None else fuzzy}


LONG_SRC = 'The relay must be earthed before the cover is removed for service'


# ── tiering ───────────────────────────────────────────────────────────────────

def test_high_fuzzy_match_is_close():
    close, related = classify_matches(LONG_SRC, [match('x', 'y', fuzzy=HTM_CLOSE_FUZZY)], 'z')
    assert len(close) == 1 and not related


def test_below_close_threshold_is_not_close():
    close, _ = classify_matches(LONG_SRC, [match('x', 'y', fuzzy=HTM_CLOSE_FUZZY - 1)], 'z')
    assert not close


def test_semantic_match_with_overlap_is_related():
    m = match('x', 'y', semantic=HTM_RELATED_SEMANTIC, fuzzy=HTM_RELATED_FUZZY)
    close, related = classify_matches(LONG_SRC, [m], 'z')
    assert not close and len(related) == 1


def test_high_semantic_without_overlap_is_dropped():
    """gte rates unrelated same-domain sentences 90-98, so semantic alone never qualifies."""
    m = match('unrelated', 'niepowiazane', semantic=98, fuzzy=HTM_RELATED_FUZZY - 1)
    close, related = classify_matches(LONG_SRC, [m], 'z')
    assert not close and not related


def test_short_source_needs_a_much_higher_fuzzy():
    """Embeddings of 1-3 word strings are noisy."""
    m = match('x', 'y', fuzzy=HTM_SHORT_FUZZY - 1)
    assert classify_matches('Test mode', [m], 'z')[0] == []
    m2 = match('x', 'y', fuzzy=HTM_SHORT_FUZZY)
    assert len(classify_matches('Test mode', [m2], 'z')[0]) == 1


def test_short_source_gets_no_related_tier():
    m = match('x', 'y', semantic=99, fuzzy=HTM_RELATED_FUZZY + 10)
    assert classify_matches('Test mode', [m], 'z')[1] == []


def test_self_echo_is_dropped():
    """This job's own targets are usually already in the TM."""
    m = match(LONG_SRC, 'Przekaznik musi byc uziemiony', fuzzy=100)
    close, related = classify_matches(LONG_SRC, [m], 'Przekaznik musi byc uziemiony')
    assert not close and not related


def test_self_echo_drop_ignores_whitespace():
    m = match(LONG_SRC, 'Przekaznik  musi   byc', fuzzy=100)
    close, _ = classify_matches(LONG_SRC, [m], 'Przekaznik musi byc')
    assert not close


def test_same_source_different_target_is_kept():
    """A TM entry disagreeing with the current target is the whole point."""
    m = match(LONG_SRC, 'Inne tlumaczenie', fuzzy=100)
    close, _ = classify_matches(LONG_SRC, [m], 'Przekaznik musi byc uziemiony')
    assert len(close) == 1


def test_number_mismatch_is_flagged():
    m = match('Rated current 240 A', 'Prad 240 A', fuzzy=95)
    close, _ = classify_matches('Rated current 140 A', [m], 'Prad 140 A')
    assert close[0]['numbers_differ'] is True


def test_matching_numbers_are_not_flagged():
    m = match('Rated current 140 A', 'Prad 140 A', fuzzy=95)
    close, _ = classify_matches('Rated current 140 A', [m], 'Inny prad')
    assert close[0]['numbers_differ'] is False


def test_tm_block_warns_about_differing_numbers():
    m = match('Rated current 240 A', 'Prad 240 A', fuzzy=95)
    close, _ = classify_matches('Rated current 140 A', [m], 'Prad 140 A')
    assert 'NUMBERS DIFFER' in build_tm_block(close, [])


def test_tm_block_marks_related_as_do_not_copy():
    m = match('other sentence', 'inne zdanie',
              semantic=HTM_RELATED_SEMANTIC, fuzzy=HTM_RELATED_FUZZY)
    _, related = classify_matches(LONG_SRC, [m], 'z')
    assert 'DO NOT copy' in build_tm_block([], related)


def test_empty_tm_block_when_nothing_qualifies():
    assert build_tm_block([], []) == ''


# ── reply parsing ─────────────────────────────────────────────────────────────

def test_plain_json_reply():
    r = parse_response('{"verdict":"FIX","suggestion":"Nowy","reason":"term"}')
    assert (r['verdict'], r['suggestion'], r['malformed']) == ('FIX', 'Nowy', False)


def test_fenced_json_reply():
    r = parse_response('```json\n{"verdict":"OK","suggestion":"","reason":"fine"}\n```')
    assert r['verdict'] == 'OK'


def test_json_with_leading_commentary():
    r = parse_response('Sure! {"verdict":"CHECK","suggestion":"","reason":"ambiguous"}')
    assert r['verdict'] == 'CHECK'


def test_unreadable_reply_becomes_check():
    """A broken reply must surface as a flag, never be silently dropped."""
    r = parse_response('I think it reads fine.')
    assert r['verdict'] == 'CHECK' and r['malformed'] is True


def test_unknown_verdict_becomes_check():
    assert parse_response('{"verdict":"WRONG","suggestion":"x"}')['verdict'] == 'CHECK'


def test_ok_verdict_discards_any_suggestion():
    r = parse_response('{"verdict":"OK","suggestion":"ignore me","reason":"fine"}')
    assert r['suggestion'] == ''


# ── suggestion guards ─────────────────────────────────────────────────────────

def base(verdict='FIX', suggestion='', reason=''):
    return {'verdict': verdict, 'suggestion': suggestion, 'reason': reason,
            'malformed': False}


def test_good_suggestion_survives():
    r = validate_suggestion('Rated current 140 A', 'Prad 240 A',
                            base(suggestion='Prad 140 A'))
    assert r['verdict'] == 'FIX' and r['suggestion'] == 'Prad 140 A'


def test_suggestion_dropping_a_tag_is_downgraded():
    """Applying it would silently destroy an inline code."""
    r = validate_suggestion('Press <1/> now', 'Nacisnij <1/> teraz',
                            base(suggestion='Nacisnij teraz'))
    assert r['verdict'] == 'CHECK' and r['suggestion'] == ''
    assert 'inline tags' in r['reason']


def test_suggestion_adding_a_tag_is_downgraded():
    r = validate_suggestion('Press <1/> now', 'Nacisnij <1/> teraz',
                            base(suggestion='Nacisnij <1/> <2/> teraz'))
    assert r['verdict'] == 'CHECK'


def test_suggestion_reordering_tags_is_downgraded():
    r = validate_suggestion('A <1/> B <2/>', 'A <1/> B <2/>',
                            base(suggestion='A <2/> B <1/>'))
    assert r['verdict'] == 'CHECK'


def test_suggestion_keeping_tags_survives():
    r = validate_suggestion('Press <1/> now', 'Nacisnij <1/> teraz',
                            base(suggestion='Wcisnij <1/> teraz'))
    assert r['verdict'] == 'FIX'


def test_invented_number_is_downgraded():
    """The TM is full of near-identical sentences with different numbers."""
    r = validate_suggestion('Rated current 140 A', 'Prad znamionowy',
                            base(suggestion='Prad znamionowy 240 A'))
    assert r['verdict'] == 'CHECK' and '240' in r['reason']


def test_number_taken_from_the_source_is_allowed():
    r = validate_suggestion('Rated current 140 A', 'Prad znamionowy',
                            base(suggestion='Prad znamionowy 140 A'))
    assert r['verdict'] == 'FIX'


def test_number_already_in_the_target_is_allowed():
    r = validate_suggestion('Rated current', 'Prad 140 A',
                            base(suggestion='Prad znamionowy 140 A'))
    assert r['verdict'] == 'FIX'


def test_fix_without_suggestion_becomes_check():
    assert validate_suggestion('a', 'b', base(suggestion=''))['verdict'] == 'CHECK'


def test_suggestion_equal_to_target_becomes_ok():
    """No point showing a fix that changes nothing."""
    r = validate_suggestion('Rated current', 'Prad  znamionowy',
                            base(suggestion='Prad znamionowy'))
    assert r['verdict'] == 'OK'


def test_check_verdict_is_left_alone():
    r = validate_suggestion('a', 'b', base(verdict='CHECK', reason='unsure'))
    assert r['verdict'] == 'CHECK' and r['reason'] == 'unsure'


# ── exact / context match exclusion ───────────────────────────────────────────
#
# 100%, 101% and context matches come out of the TM unchanged, so reviewing them
# against that same TM only re-litigates the TM's own content. They are skipped
# in every scope, whether or not they are confirmed.

from Xedaibt import XLIFFEditor  # noqa: E402

is_exact = XLIFFEditor._is_exact_match


def seg(match='', percent='', state='translated'):
    return {'match': match, 'match_percent': percent, 'state': state}


@pytest.mark.parametrize('segment', [
    seg('CM', '101'),                      # Phrase: m:score 1.01
    seg('CM', '100'),                      # SDL: percent 100 + Context Match system
    seg('CM', ''),                         # label only
    seg('100%', '100'),
    seg('101%', '101'),
    seg('', '100'),                        # percent only, no label
    seg('', '101'),
])
def test_exact_and_context_matches_are_skipped(segment):
    assert is_exact(segment) is True


@pytest.mark.parametrize('segment', [
    seg('99%', '99'),
    seg('75%', '75'),
    seg('MT', ''),                         # machine translation always reviewable
    seg('MT', '0'),
    seg('TM', ''),                         # origin known, no score
    seg('', ''),                           # plain XLIFF with no match data
])
def test_everything_else_is_reviewable(segment):
    assert is_exact(segment) is False


def test_skipping_ignores_confirmation_state():
    """The rule cuts across the scope selector: confirmed or not, they are out."""
    for state in ('final', 'reviewed', 'translated', 'initial'):
        assert is_exact(seg('CM', '101', state)) is True
        assert is_exact(seg('100%', '100', state)) is True
        assert is_exact(seg('99%', '99', state)) is False


def test_label_percent_is_used_when_percent_field_is_missing():
    assert is_exact(seg('100%', '')) is True
    assert is_exact(seg('99%', '')) is False


def test_unparseable_percent_does_not_skip():
    """A malformed score must not quietly drop the segment from the review."""
    assert is_exact(seg('', 'not-a-number')) is False
    assert is_exact({'match': None, 'match_percent': None}) is False


# ── token-saving levers ───────────────────────────────────────────────────────

from tm_review import (  # noqa: E402
    MAX_TOKENS, MAX_TOKENS_CAP, REASONING_BUDGET, Usage,
    filter_glossary_to_sources, format_glossary,
)

GLOSSARY = {
    'relay': 'przekaźnik',
    'circuit breaker': 'wyłącznik',
    'fault': 'usterka',
    'harvester': 'kombajn',
}


def test_glossary_keeps_only_terms_present_in_the_job():
    """An unfiltered termbase re-sent on every call is what dominates the bill."""
    kept = filter_glossary_to_sources(GLOSSARY, ['The relay reports a fault'])
    assert set(kept) == {'relay', 'fault'}


def test_glossary_matches_plurals():
    kept = filter_glossary_to_sources(GLOSSARY, ['Two relays and three faults'])
    assert set(kept) == {'relay', 'fault'}


def test_glossary_matches_across_flexible_whitespace():
    """A source may hyphenate or line-wrap where the termbase does not."""
    assert 'circuit breaker' in filter_glossary_to_sources(
        GLOSSARY, ['the circuit-breaker tripped'])
    assert 'circuit breaker' in filter_glossary_to_sources(
        GLOSSARY, ['the circuit\nbreaker tripped'])


def test_glossary_respects_word_boundaries():
    """'relay' must not be found inside 'relayed' or 'underlay'."""
    assert filter_glossary_to_sources({'relay': 'x'}, ['the message was relayed']) == {}
    assert filter_glossary_to_sources({'lay': 'x'}, ['underlay']) == {}


def test_empty_glossary_is_handled():
    assert filter_glossary_to_sources({}, ['anything']) == {}
    assert filter_glossary_to_sources(None, ['anything']) == {}


def test_format_glossary_is_empty_when_nothing_kept():
    assert format_glossary({}) == ''


def test_format_glossary_lists_kept_terms():
    out = format_glossary({'relay': 'przekaźnik'})
    assert 'relay' in out and 'przekaźnik' in out


# ── usage accounting ──────────────────────────────────────────────────────────

class _Details:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Usage:
    def __init__(self, prompt=100, completion=50, reasoning=10, cached=0, cost=0.01):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.completion_tokens_details = _Details(reasoning_tokens=reasoning)
        self.prompt_tokens_details = _Details(cached_tokens=cached)
        self.cost = cost


class _Response:
    def __init__(self, usage=None, discount=0.0):
        self.usage = usage
        self.cache_discount = discount


def test_usage_accumulates_across_calls():
    u = Usage()
    u.record(_Response(_Usage()))
    u.record(_Response(_Usage()))
    assert (u.calls, u.tokens_in, u.tokens_out, u.reasoning) == (2, 200, 100, 20)
    assert u.cost == pytest.approx(0.02)


def test_usage_survives_a_response_with_no_usage_block():
    """Provider-reported fields may be absent; accounting must not raise."""
    u = Usage()
    u.record(_Response(None))
    assert u.calls == 1 and u.tokens_in == 0


def test_usage_reads_detail_dicts_as_well_as_objects():
    u = Usage()
    usage = _Usage()
    usage.completion_tokens_details = {'reasoning_tokens': 7}
    usage.prompt_tokens_details = {'cached_tokens': 3}
    u.record(_Response(usage))
    assert u.reasoning == 7 and u.cached == 3


def test_summary_flags_when_no_caching_happened():
    u = Usage()
    u.record(_Response(_Usage(cached=0)))
    assert 'no caching seen' in u.summary()


def test_summary_omits_the_flag_when_caching_worked():
    u = Usage()
    u.record(_Response(_Usage(cached=80)))
    assert 'no caching seen' not in u.summary()


def test_summary_reports_repeat_cache_hits():
    u = Usage()
    u.record(_Response(_Usage()))
    u.cache_hits = 103
    assert '103 segment(s) answered from the repeat cache' in u.summary()


def test_summary_without_calls_says_so():
    assert Usage().summary() == 'No model calls were made.'


def test_reasoning_budget_is_pinned_absolutely():
    """An effort level is a fraction of max_tokens and drifts; a budget does not."""
    assert isinstance(REASONING_BUDGET, int) and REASONING_BUDGET > 0
    assert MAX_TOKENS_CAP > MAX_TOKENS
