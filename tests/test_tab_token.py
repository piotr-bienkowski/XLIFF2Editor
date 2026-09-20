"""A literal tab in segment content is shown as <t/> and restored on save.

Tabs matter in DTP formats: in an IDML table of contents they are the stops
that push the page numbers to the right margin.  They are invisible in the
grid, cannot be typed into a cell (Tab moves focus), and a tab that is the
whole text node between two inline tags used to be collapsed to a space by
BeautifulSoup before it ever reached the editor.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bs4 import BeautifulSoup

from Xedaibt import (
    PRESERVE_WS_TAGS,
    TAB_TOKEN,
    build_xml_fragment,
    parse_tags_from_element,
)

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'

# The ProfiHopper TOC line: number, tab, title, tab, page range.
TOC_SOURCE = (
    f'<source xmlns="{NS22}" xml:space="preserve">'
    '<pc id="68"/><pc id="70">7.</pc>'
    '<pc id="71">\tBedienung, Steuerung und Messertausch</pc>'
    '<pc id="72">\t<pc id="73">20 – 22</pc></pc>'
    '</source>'
)


def _soup(markup):
    return BeautifulSoup(markup, 'xml', preserve_whitespace_tags=PRESERVE_WS_TAGS)


def test_whitespace_only_text_node_survives_parsing():
    """Without preserve_whitespace_tags bs4 turns a lone tab into a space."""
    source = _soup(TOC_SOURCE).find('source')
    assert source.find('pc', id='72').get_text().startswith('\t')


def test_tabs_become_tokens_in_the_grid():
    source = _soup(TOC_SOURCE).find('source')
    text, _ = parse_tags_from_element(source)

    assert text == (
        '<1></1><2>7.</2>'
        '<3><t/>Bedienung, Steuerung und Messertausch</3>'
        '<4><t/><5>20 – 22</5></4>'
    )
    assert '\t' not in text
    assert text.count(TAB_TOKEN) == 2


def test_tokens_become_tabs_again_on_save():
    source = _soup(TOC_SOURCE).find('source')
    text, tag_map = parse_tags_from_element(source)

    fragment = build_xml_fragment(text, tag_map)

    assert fragment.count('\t') == 2
    assert TAB_TOKEN not in fragment
    assert '<pc id="72">\t<pc id="73">' in fragment
    # Thin spaces around the en dash are content, not markup, and stay put.
    assert fragment.count(' ') == 2


def test_round_trip_through_the_fragment_soup():
    """serialize_to_xml re-parses the fragment; the tab must survive that too."""
    source = _soup(TOC_SOURCE).find('source')
    text, tag_map = parse_tags_from_element(source)

    fragment = _soup(f'<root>{build_xml_fragment(text, tag_map)}</root>')

    assert fragment.root.find('pc', id='72').get_text().startswith('\t')


def test_translator_can_move_the_token():
    """The token is ordinary text in the cell, so it reorders with the words."""
    source = _soup(TOC_SOURCE).find('source')
    _, tag_map = parse_tags_from_element(source)

    typed = '<1></1><2>7.</2><3><t/>Obsługa i wymiana noży</3><4><t/><5>20 – 22</5></4>'
    fragment = build_xml_fragment(typed, tag_map)

    assert '<pc id="71">\tObsługa i wymiana noży</pc>' in fragment
    assert fragment.count('\t') == 2


def test_stray_tab_token_without_tags_still_becomes_a_tab():
    text, tag_map = 'Kolumna A<t/>Kolumna B', {}
    assert build_xml_fragment(text, tag_map) == 'Kolumna A\tKolumna B'
