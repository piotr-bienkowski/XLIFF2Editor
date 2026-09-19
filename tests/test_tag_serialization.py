"""
Tag round-trip safety: grid text must never produce broken XML.

The grid renders inline tags as numbered tokens (<1/> standalone, <1>...</1>
paired) and everything else as literal text.  Translators legitimately type
'&', '<' and '>', and they can delete half of a paired token, so these tests
pin down that neither can corrupt the saved file.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from bs4 import BeautifulSoup
from lxml import etree

from Xedaibt import build_xml_fragment, parse_tags_from_element

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'


# ── helpers ───────────────────────────────────────────────────────────────────

def _target(inner_xml):
    """Parse a <target> holding *inner_xml* the way the editor loads a file."""
    soup = BeautifulSoup(
        f'<target xmlns="{NS22}" xml:space="preserve">{inner_xml}</target>', 'xml'
    )
    return soup.find('target')


def _round_trip(inner_xml):
    """Load a target, then save it back: returns the re-serialised inner XML."""
    element = _target(inner_xml)
    text, tag_map = parse_tags_from_element(element)
    return text, build_xml_fragment(text, tag_map)


def _is_well_formed(fragment_xml):
    try:
        etree.fromstring(f'<root>{fragment_xml}</root>')
        return True
    except etree.XMLSyntaxError:
        return False


def _text_of(fragment_xml):
    return ''.join(etree.fromstring(f'<root>{fragment_xml}</root>').itertext())


# ── literal characters that are XML metacharacters ────────────────────────────

@pytest.mark.parametrize('literal', [
    'A & B',
    'A < B',
    'A > B',
    'a < b && c > d',
    'Tom & Jerry <best> & friends',
    'if (a<b) { return a&b; }',
    'Znaki specjalne !"#%&\'()*+-./:;<=>?@[\\]^_`{|}~',
    '5 < 6 & 7 > 3',
])
def test_literal_metacharacters_survive(literal):
    """The bug this suite exists for: '&' and '<' were silently swallowed."""
    text, fragment = _round_trip(literal.replace('&', '&amp;')
                                        .replace('<', '&lt;')
                                        .replace('>', '&gt;'))
    assert text == literal
    assert _is_well_formed(fragment)
    assert _text_of(fragment) == literal


def test_ampersand_is_not_dropped():
    _, fragment = _round_trip('A &amp; B &lt; C')
    assert _text_of(fragment) == 'A & B < C'


def test_literal_text_with_tags_around_it():
    _, fragment = _round_trip('<ph id="1"/>a &amp; b<ph id="2"/>')
    assert _is_well_formed(fragment)
    assert _text_of(fragment) == 'a & b'
    assert fragment.count('<ph') == 2


# ── attribute values needing quoting ──────────────────────────────────────────

def test_attribute_with_quotes_stays_well_formed():
    """Some importers put raw markup in an attribute; it must not break the tag."""
    _, fragment = _round_trip('<ph id="1" x-orig="&lt;w:r w:val=&quot;x&quot;/&gt;"/>')
    assert _is_well_formed(fragment)
    root = etree.fromstring(f'<root>{fragment}</root>')
    assert root[0].get('x-orig') == '<w:r w:val="x"/>'


def test_attribute_with_ampersand_stays_well_formed():
    _, fragment = _round_trip('<ph id="1" type="a&amp;b"/>')
    assert _is_well_formed(fragment)
    assert etree.fromstring(f'<root>{fragment}</root>')[0].get('type') == 'a&b'


# ── nested paired tags ────────────────────────────────────────────────────────

def test_nested_pairs_get_distinct_numbers():
    """Nested <pc> used to collapse onto the same token and lose the inner ids."""
    text, tag_map = parse_tags_from_element(
        _target('<pc id="1"><pc id="2"><pc id="3">x</pc></pc></pc>')
    )
    assert text == '<1><2><3>x</3></2></1>'
    assert [tag_map[k]['attrs']['id'] for k in sorted(tag_map)] == ['1', '2', '3']


def test_nested_pairs_round_trip_with_original_ids():
    _, fragment = _round_trip('<pc id="1"><pc id="2"><pc id="3">x</pc></pc></pc>')
    root = etree.fromstring(f'<root>{fragment}</root>')
    assert [e.get('id') for e in root.iter('pc')] == ['1', '2', '3']


def test_nested_pairs_keep_surrounding_text():
    text, fragment = _round_trip(
        'go to <pc id="1">the <pc id="2">deep</pc> end</pc> now'
    )
    assert text == 'go to <1>the <2>deep</2> end</1> now'
    assert _text_of(fragment) == 'go to the deep end now'


def test_numbering_is_document_order():
    """_current_source_signature and the tag-insert shortcut sort on these keys."""
    _, tag_map = parse_tags_from_element(
        _target('<ph id="a"/><pc id="b"><ph id="c"/></pc><ph id="d"/>')
    )
    assert [tag_map[k]['attrs']['id'] for k in sorted(tag_map)] == ['a', 'b', 'c', 'd']


# ── half-deleted and malformed tokens ─────────────────────────────────────────

def test_unclosed_paired_token_is_closed():
    _, tag_map = parse_tags_from_element(_target('<pc id="1">x</pc>'))
    fragment = build_xml_fragment('<1>x', tag_map)      # translator deleted </1>
    assert _is_well_formed(fragment)
    assert _text_of(fragment) == 'x'


def test_orphan_closing_token_stays_literal():
    _, tag_map = parse_tags_from_element(_target('<pc id="1">x</pc>'))
    fragment = build_xml_fragment('x</1>', tag_map)     # translator deleted <1>
    assert _is_well_formed(fragment)
    assert _text_of(fragment) == 'x</1>'


def test_crossed_tokens_stay_well_formed():
    _, tag_map = parse_tags_from_element(
        _target('<pc id="1">a</pc><pc id="2">b</pc>')
    )
    fragment = build_xml_fragment('<1>a<2>b</1></2>', tag_map)
    assert _is_well_formed(fragment)


def test_token_for_unknown_tag_stays_literal():
    _, tag_map = parse_tags_from_element(_target('<ph id="1"/>'))
    fragment = build_xml_fragment('keep <9/> and <1/>', tag_map)
    assert _is_well_formed(fragment)
    assert _text_of(fragment) == 'keep <9/> and '
    assert fragment.count('<ph') == 1


def test_wrong_token_shape_stays_literal():
    """<1/> for a paired tag, or <1> for a standalone one, is not a tag."""
    _, paired_map = parse_tags_from_element(_target('<pc id="1">x</pc>'))
    assert _text_of(build_xml_fragment('<1/>', paired_map)) == '<1/>'

    _, single_map = parse_tags_from_element(_target('<ph id="1"/>'))
    assert _text_of(build_xml_fragment('<1>x</1>', single_map)) == '<1>x</1>'


def test_all_tags_deleted_is_plain_text():
    _, tag_map = parse_tags_from_element(_target('<ph id="1"/>hello<ph id="2"/>'))
    fragment = build_xml_fragment('hello', tag_map)
    assert _is_well_formed(fragment)
    assert fragment == 'hello'


def test_empty_text_is_valid():
    _, tag_map = parse_tags_from_element(_target('<ph id="1"/>'))
    assert build_xml_fragment('', tag_map) == ''


# ── standalone tags carrying content ──────────────────────────────────────────

def test_standalone_tag_content_is_preserved():
    """memoQ writes the original code inside <ph>; saving used to discard it."""
    text, fragment = _round_trip('<ph id="1">&lt;w:br/&gt;</ph>')
    assert text == '<1/>'
    assert _is_well_formed(fragment)
    root = etree.fromstring(f'<root>{fragment}</root>')
    assert root[0].text == '<w:br/>'


def test_empty_standalone_tag_stays_self_closing():
    _, fragment = _round_trip('<ph id="1"/>')
    assert fragment == '<ph id="1"/>'


# ── shapes the converters actually emit ───────────────────────────────────────

@pytest.mark.parametrize('inner', [
    'plain text',
    '<ph id="1"/>',
    'a<ph id="1"/>b',
    '<pc id="1">bold</pc>',
    '<sc id="1"/>text<ec startRef="1"/>',            # Phrase flat codes
    '<pc id="1">outer <pc id="2">inner</pc></pc>',
    '<ph id="1"/><ph id="2"/><ph id="3"/>',
    'A &amp; B <ph id="1"/> C &lt; D',
])
def test_round_trip_is_stable(inner):
    """Loading and saving without editing must not change the content."""
    text, first = _round_trip(inner)
    text_again, second = _round_trip(first)
    assert text_again == text
    assert second == first
    assert _is_well_formed(first)
