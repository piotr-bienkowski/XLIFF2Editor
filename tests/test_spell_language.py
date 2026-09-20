"""Spell-check dictionary resolution.

The old code mapped eight languages by hand and fell back to f'{lang}_US',
so a Dutch target asked Enchant for 'nl_US' - a locale that cannot exist -
and the real message (no Dutch dictionary installed) was buried.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from Xedaibt import resolve_enchant_language

# What this machine actually has installed.
INSTALLED = [
    'en', 'en-variant_0', 'en-variant_1', 'en-w_accents', 'en-wo_accents',
    'en_AU', 'en_AU-variant_0', 'en_CA', 'en_GB', 'en_GB-ise', 'en_GB-ize',
    'en_US', 'en_US-variant_0', 'en_US-w_accents', 'pl_PL',
]


@pytest.mark.parametrize('code,expected', [
    ('pl-PL', 'pl_PL'),
    ('pl_PL', 'pl_PL'),
    ('pl-pl', 'pl_PL'),     # the ABB files are lower-case throughout
    ('pl', 'pl_PL'),        # region-less code finds the only Polish dictionary
    ('en-GB', 'en_GB'),
    ('en-US', 'en_US'),
    ('en', 'en_US'),        # several regions installed: the documented default
])
def test_resolves_installed_languages(code, expected):
    assert resolve_enchant_language(code, INSTALLED) == expected


@pytest.mark.parametrize('code', ['nl-NL', 'nl', 'de-DE', 'zh-Hans-CN'])
def test_missing_language_resolves_to_none(code):
    """No dictionary is better than a fabricated locale like nl_US."""
    assert resolve_enchant_language(code, INSTALLED) is None


def test_unknown_region_falls_back_within_the_language():
    assert resolve_enchant_language('en-NZ', INSTALLED) == 'en_US'


def test_plain_dictionary_beats_a_spelling_variant():
    assert resolve_enchant_language('en-GB', ['en_GB-ise', 'en_GB']) == 'en_GB'
    # ...but a variant is still better than nothing.
    assert resolve_enchant_language('en-GB', ['en_GB-ise']) == 'en_GB-ise'


def test_language_without_hardcoded_mapping_is_found():
    """'nl' used to be unmappable; now it just needs the dictionary present."""
    assert resolve_enchant_language('nl-NL', ['nl_NL', 'pl_PL']) == 'nl_NL'
    assert resolve_enchant_language('nl', ['nl_NL', 'pl_PL']) == 'nl_NL'


def test_regional_preference_is_honoured_then_exactness_wins():
    both = ['pt_BR', 'pt_PT']
    assert resolve_enchant_language('pt', both) == 'pt_BR'
    assert resolve_enchant_language('pt-PT', both) == 'pt_PT'


def test_missing_or_empty_code_defaults_to_english():
    assert resolve_enchant_language(None, INSTALLED) == 'en_US'
    assert resolve_enchant_language('', INSTALLED) == 'en_US'
    assert resolve_enchant_language('  ', INSTALLED) == 'en_US'


def test_no_dictionaries_at_all():
    assert resolve_enchant_language('pl-PL', []) is None
