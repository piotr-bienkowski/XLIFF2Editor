"""The Set Target Language dialog offers a fixed list instead of free text.

A free-text box let 'nl-US' and similar non-locales reach the file's trgLang,
where they then drove the spell checker and the merged target-language.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import re

import pytest

from Xedaibt import (
    DEFAULT_TARGET_LANGUAGE,
    EUROPEAN_LANGUAGES,
    language_choices,
    resolve_enchant_language,
)

BCP47 = re.compile(r'^[a-z]{2,3}(-[A-Z][a-z]{3})?-[A-Z]{2}$')


def test_every_offered_code_is_well_formed():
    for code, name in EUROPEAN_LANGUAGES:
        assert BCP47.match(code), code
        assert name


def test_codes_are_unique_and_sorted_by_name():
    codes = [code for code, _ in EUROPEAN_LANGUAGES]
    assert len(codes) == len(set(codes))
    names = [name for _, name in EUROPEAN_LANGUAGES]
    assert names == sorted(names)


def test_the_eu_languages_and_en_us_are_all_there():
    codes = {code for code, _ in EUROPEAN_LANGUAGES}
    eu = {
        'bg-BG', 'hr-HR', 'cs-CZ', 'da-DK', 'nl-NL', 'en-IE', 'et-EE', 'fi-FI',
        'fr-FR', 'de-DE', 'el-GR', 'hu-HU', 'ga-IE', 'it-IT', 'lv-LV', 'lt-LT',
        'mt-MT', 'pl-PL', 'pt-PT', 'ro-RO', 'sk-SK', 'sl-SI', 'es-ES', 'sv-SE',
    }
    assert eu <= codes
    assert 'en-US' in codes


def test_entry_text_starts_with_the_code():
    entries, _ = language_choices()
    for entry, (code, _name) in zip(entries, EUROPEAN_LANGUAGES):
        assert entry.split()[0] == code


@pytest.mark.parametrize('current,expected', [
    ('pl-PL', 'pl-PL'),
    ('pl-pl', 'pl-PL'),       # the file's own casing must still match
    ('de-de', 'de-DE'),
    (None, DEFAULT_TARGET_LANGUAGE),
    ('', DEFAULT_TARGET_LANGUAGE),
])
def test_current_language_is_preselected(current, expected):
    entries, index = language_choices(current)
    assert entries[index].split()[0] == expected


def test_a_non_european_code_on_the_file_is_kept():
    """Opening a Japanese job must not force a different target language."""
    entries, index = language_choices('ja-JP')
    assert index == 0
    assert entries[0].split()[0] == 'ja-JP'
    assert len(entries) == len(EUROPEAN_LANGUAGES) + 1


def test_offered_codes_resolve_for_spell_checking():
    """Each code finds its own dictionary, were it installed."""
    for code, _ in EUROPEAN_LANGUAGES:
        installed = [code.replace('-', '_')]
        assert resolve_enchant_language(code, installed) == installed[0]
