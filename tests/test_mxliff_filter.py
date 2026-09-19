import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import tempfile
from xml.sax.saxutils import escape

import pytest
from lxml import etree

from mxliff_xliff22_converter import (
    build_xliff22_content,
    compute_match_label,
    convert_mxliff_to_xliff22,
    map_mxliff_state,
    parse_phrase_tags,
    read_marks,
)
from xliff22_to_mxliff_merger import (
    map_state_to_confirmed,
    merge_xliff22_to_mxliff,
    serialize_to_phrase,
)

NS22 = 'urn:oasis:names:tc:xliff:document:2.0'
NS12 = 'urn:oasis:names:tc:xliff:document:1.2'
NSM = 'http://www.memsource.com/mxlf/2.0'

_TEMP_FILES: list = []


def teardown_module(_module):
    import os
    for p in _TEMP_FILES:
        try:
            os.unlink(p)
        except OSError:
            pass


# ── helpers ───────────────────────────────────────────────────────────────────

def _tmp(suffix: str) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.close()
    _TEMP_FILES.append(tmp.name)
    return Path(tmp.name)


def _make_mxliff(units, files=None, m_version='2.17') -> Path:
    """
    Build a minimal .mxliff.

    units: list of dicts with keys source, target, and optionally confirmed,
           locked, score, origin, marks (list of (id, type, content)), task.
    files: list of (original, task_id, units) to build a joined job instead.
    """
    if files is None:
        files = [('doc.docx', 'TASK1', units)]

    parts = [
        "<?xml version='1.0' encoding='UTF-8'?>",
        f'<xliff xmlns="{NS12}" xmlns:m="{NSM}" version="1.2" '
        f'm:version="{m_version}" m:level="1">',
    ]
    for original, task_id, file_units in files:
        parts.append(
            f'<file original="{original}" source-language="en-us" '
            f'target-language="pl-pl" datatype="x-undefined" '
            f'm:task-id="{task_id}">\n<body>'
        )
        for index, unit in enumerate(file_units):
            marks = unit.get('marks') or []
            meta = ''
            if marks:
                mark_xml = ''.join(
                    f'<m:mark id="{mid}">'
                    + (f'<m:type>{mtype}</m:type>' if mtype else '')
                    + f'<m:content>{content}</m:content></m:mark>'
                    for mid, mtype, content in marks
                )
                meta = (f'<m:tunit-metadata>{mark_xml}</m:tunit-metadata>'
                        f'<m:tunit-target-metadata>{mark_xml}</m:tunit-target-metadata>')
            parts.append(
                f'<group id="{index}" m:para-id="{index}">'
                f'<trans-unit id="{task_id}:{index}" xml:space="preserve" '
                f'm:score="{unit.get("score", "1.0")}" '
                f'm:trans-origin="{unit.get("origin", "tm")}" '
                f'm:confirmed="{unit.get("confirmed", "0")}" '
                f'm:locked="{unit.get("locked", "false")}" '
                f'm:para-id="{index}" m:level-edited="false">'
                # Phrase escapes '<' and '&' in segment text, so the closing
                # half of a paired code reads '&lt;1}' in the file itself.
                f'<source>{escape(unit["source"])}</source>'
                f'<target>{escape(unit.get("target", ""))}</target>'
                f'{meta}</trans-unit></group>'
            )
        parts.append('</body>\n</file>')
    parts.append('</xliff>')

    path = _tmp('.mxliff')
    path.write_text('\n'.join(parts), encoding='utf-8')
    return path


def _units_of(xliff_path):
    root = etree.parse(str(xliff_path)).getroot()
    return root.findall(f'.//{{{NS22}}}unit')


def _trans_units_of(mxliff_path):
    parser = etree.XMLParser(strip_cdata=False, resolve_entities=False)
    root = etree.parse(str(mxliff_path), parser).getroot()
    return root.findall(f'.//{{{NS12}}}trans-unit')


def _text(elem):
    return ''.join(elem.itertext()) if elem is not None else None


# ── brace notation parsing ────────────────────────────────────────────────────

def test_parse_standalone_tag():
    assert parse_phrase_tags('a {1} b') == ['a ', ('ph', '1'), ' b']


def test_parse_paired_tag():
    assert parse_phrase_tags('{1>x<1}') == [('sc', '1'), 'x', ('ec', '1')]


def test_parse_letter_tag():
    """Intrinsic formatting codes use a letter id and carry no metadata mark."""
    assert parse_phrase_tags('{b>bold<b}') == [('sc', 'b'), 'bold', ('ec', 'b')]
    assert parse_phrase_tags('{B>x<B}') == [('sc', 'B'), 'x', ('ec', 'B')]


def test_parse_nested_paired_tags():
    assert parse_phrase_tags('{1>{2>t<2}<1}') == [
        ('sc', '1'), ('sc', '2'), 't', ('ec', '2'), ('ec', '1')
    ]


def test_parse_empty_paired_tag():
    assert parse_phrase_tags('{2><2}') == [('sc', '2'), ('ec', '2')]


def test_parse_leaves_literal_braces_alone():
    """Text that only looks like the notation must survive verbatim."""
    for literal in ('cost {approx} 5', 'a } b', '{ 1 }', 'set {x to 1'):
        assert parse_phrase_tags(literal) == [literal]


def test_parse_multi_digit_ids():
    assert parse_phrase_tags('{12}{13>x<13}') == [
        ('ph', '12'), ('sc', '13'), 'x', ('ec', '13')
    ]


# ── brace notation <-> XLIFF 2.2 inline elements ──────────────────────────────

def test_build_content_emits_flat_codes():
    """Paired codes become sc/ec, never nested pc: Phrase's model is flat."""
    parts = build_xliff22_content('{1>x<1}')
    names = [etree.QName(p).localname for p in parts if not isinstance(p, str)]
    assert names == ['sc', 'ec']
    assert 'pc' not in names


def test_build_content_sets_ids_and_startref():
    parts = build_xliff22_content('{1>x<1} {2}')
    elems = [p for p in parts if not isinstance(p, str)]
    assert elems[0].get('id') == '1'
    assert elems[1].get('startRef') == '1'
    assert elems[2].get('id') == '2'


def test_build_content_applies_mark_type():
    parts = build_xliff22_content('{1}', {'1': {'type': 'code', 'content': '<w:r/>'}})
    elem = [p for p in parts if not isinstance(p, str)][0]
    assert elem.get('type') == 'code'


def test_build_content_omits_bulky_mark_content():
    """
    The mark's original markup must not be copied onto the element: it can run
    to hundreds of characters and contains quotes that the editor's attribute
    serializer would emit unescaped.
    """
    huge = '<term class="- topic/term " id="x">'
    parts = build_xliff22_content('{1}', {'1': {'type': 'term', 'content': huge}})
    elem = [p for p in parts if not isinstance(p, str)][0]
    assert all('term class' not in (v or '') for v in elem.attrib.values())


@pytest.mark.parametrize('text', [
    'plain text',
    'a {1} b',
    '{1>x<1}',
    '{b>bold<b}',
    '{1>{2>deep<2}<1}',
    '{2><2}',
    'mix {1} and {2>y<2} end',
])
def test_brace_notation_round_trip(text):
    """build -> serialize must reproduce the Phrase text exactly."""
    holder = etree.Element(f'{{{NS22}}}target')
    parts = build_xliff22_content(text)
    for part in parts:
        if isinstance(part, str):
            if len(holder):
                holder[-1].tail = (holder[-1].tail or '') + part
            else:
                holder.text = (holder.text or '') + part
        else:
            holder.append(part)
    assert serialize_to_phrase(holder) == text


def test_serialize_accepts_pc_from_other_importers():
    holder = etree.fromstring(
        f'<target xmlns="{NS22}">a<pc id="1">x</pc>b</target>'
    )
    assert serialize_to_phrase(holder) == 'a{1>x<1}b'


# ── status and match mapping ──────────────────────────────────────────────────

def test_confirmed_maps_to_final():
    assert map_mxliff_state('1', True) == 'final'


def test_unconfirmed_with_target_is_translated():
    assert map_mxliff_state('0', True) == 'translated'


def test_unconfirmed_without_target_is_initial():
    assert map_mxliff_state('0', False) == 'initial'


@pytest.mark.parametrize('state,expected', [
    ('final', '1'), ('reviewed', '1'),
    ('translated', '0'), ('initial', '0'), ('', '0'), (None, '0'),
])
def test_state_maps_back_to_confirmed(state, expected):
    assert map_state_to_confirmed(state) == expected


def test_context_match_label():
    """Phrase writes m:score=1.01 for a 101% context match."""
    assert compute_match_label('1.01', 'tm') == 'CM'


def test_percentage_match_label():
    assert compute_match_label('1.0', 'tm') == '100%'
    assert compute_match_label('0.87', 'tm') == '87%'


def test_machine_translation_label():
    assert compute_match_label('0.0', 'mt') == 'MT'


def test_match_label_survives_bad_score():
    assert compute_match_label('not-a-number', 'tm') == 'TM'


# ── conversion ────────────────────────────────────────────────────────────────

def test_convert_produces_one_unit_per_trans_unit():
    src = _make_mxliff([
        {'source': 'One', 'target': 'Jeden'},
        {'source': 'Two', 'target': 'Dwa'},
    ])
    out = _tmp('.xlf')
    result = convert_mxliff_to_xliff22([src], out, verbose=False)
    assert result['total_segments'] == 2
    assert len(_units_of(out)) == 2


def test_convert_uses_trans_unit_id_as_unit_id():
    src = _make_mxliff([{'source': 'One', 'target': 'Jeden'}])
    out = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], out, verbose=False)
    assert _units_of(out)[0].get('id') == 'TASK1:0'


def test_convert_marks_provenance():
    """The merger and the editor's export guard both key off this attribute."""
    src = _make_mxliff([{'source': 'One', 'target': 'Jeden'}])
    out = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], out, verbose=False)
    assert _units_of(out)[0].get('x-mxliff-origin') == 'phrase'


def test_convert_keeps_joined_files_separate():
    src = _make_mxliff(None, files=[
        ('a.docx', 'TASKA', [{'source': 'One', 'target': 'Jeden'}]),
        ('b.xml', 'TASKB', [{'source': 'Two', 'target': 'Dwa'}]),
    ])
    out = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], out, verbose=False)
    root = etree.parse(str(out)).getroot()
    files = root.findall(f'{{{NS22}}}file')
    assert [f.get('original') for f in files] == ['a.docx', 'b.xml']


def test_joined_files_with_colliding_group_ids_stay_distinct():
    """
    Group ids restart at 0 in every file of a joined job, so they collide.
    Unit ids carry the task-id prefix and must remain unique.
    """
    src = _make_mxliff(None, files=[
        ('a.docx', 'TASKA', [{'source': 'One', 'target': 'Jeden'}]),
        ('b.xml', 'TASKB', [{'source': 'Two', 'target': 'Dwa'}]),
    ])
    out = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], out, verbose=False)
    units = _units_of(out)
    assert [u.get('x-mxliff-group') for u in units] == ['0', '0']   # collide
    assert len({u.get('id') for u in units}) == 2                   # do not


def test_duplicate_file_names_get_disambiguated():
    src = _make_mxliff(None, files=[
        ('same.docx', 'TASKA', [{'source': 'One', 'target': 'Jeden'}]),
        ('same.docx', 'TASKB', [{'source': 'Two', 'target': 'Dwa'}]),
    ])
    out = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], out, verbose=False)
    root = etree.parse(str(out)).getroot()
    ids = [f.get('id') for f in root.findall(f'{{{NS22}}}file')]
    assert len(set(ids)) == 2


def test_locked_segment_becomes_untranslatable():
    src = _make_mxliff([{'source': 'One', 'target': 'Jeden', 'locked': 'true'}])
    out = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], out, verbose=False)
    seg = _units_of(out)[0].find(f'{{{NS22}}}segment')
    assert seg.get('translate') == 'no'


def test_skip_locked_omits_locked_segments():
    src = _make_mxliff([
        {'source': 'One', 'target': 'Jeden', 'locked': 'true'},
        {'source': 'Two', 'target': 'Dwa'},
    ])
    out = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], out, verbose=False, skip_locked=True)
    assert len(_units_of(out)) == 1


def test_convert_reads_attributes_regardless_of_order():
    """Phrase 2.13 writes attributes alphabetically; 2.16+ does not."""
    path = _tmp('.mxliff')
    path.write_text(
        "<?xml version='1.0' encoding='UTF-8'?>"
        f'<xliff xmlns="{NS12}" xmlns:m="{NSM}" version="1.2" m:version="2.13">'
        f'<file datatype="x-undefined" original="d.docx" source-language="en-ca" '
        f'target-language="pl-pl" m:task-id="T" m:file-format="DOC"><body>'
        f'<group id="0"><trans-unit m:confirmed="1" m:locked="false" '
        f'm:score="1.0" m:trans-origin="tm" id="T:0" xml:space="preserve">'
        f'<source>One</source><target>Jeden</target>'
        f'</trans-unit></group></body></file></xliff>',
        encoding='utf-8',
    )
    out = _tmp('.xlf')
    convert_mxliff_to_xliff22([path], out, verbose=False)
    seg = _units_of(out)[0].find(f'{{{NS22}}}segment')
    assert seg.get('state') == 'final'


def test_empty_source_is_skipped():
    src = _make_mxliff([
        {'source': '', 'target': ''},
        {'source': 'Two', 'target': 'Dwa'},
    ])
    out = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], out, verbose=False)
    assert len(_units_of(out)) == 1


def test_read_marks_collects_type_and_content():
    src = _make_mxliff([{'source': '{1}', 'target': '{1}',
                         'marks': [('1', 'code', 'w:r')]}])
    root = etree.parse(str(src)).getroot()
    trans_unit = root.find(f'.//{{{NS12}}}trans-unit')
    marks = read_marks(trans_unit, 'tunit-metadata')
    assert marks['1']['type'] == 'code'
    assert marks['1']['content'] == 'w:r'


def test_converter_rejects_non_mxliff():
    path = _tmp('.mxliff')
    path.write_text('<?xml version="1.0"?><notxliff/>', encoding='utf-8')
    with pytest.raises(ValueError):
        convert_mxliff_to_xliff22([path], _tmp('.xlf'), verbose=False)


# ── merging back ──────────────────────────────────────────────────────────────

def test_merge_writes_edited_target():
    src = _make_mxliff([{'source': 'One', 'target': 'Jeden'}])
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], xlf, verbose=False)

    tree = etree.parse(str(xlf))
    tree.getroot().find(f'.//{{{NS22}}}target').text = 'Nowy'
    tree.write(str(xlf), encoding='utf-8', xml_declaration=True)

    out = _tmp('.mxliff')
    result = merge_xliff22_to_mxliff(xlf, src, out)
    assert result['updated'] == 1
    assert _text(_trans_units_of(out)[0].find(f'{{{NS12}}}target')) == 'Nowy'


def test_merge_is_lossless_when_nothing_changed():
    src = _make_mxliff([
        {'source': 'One {1}', 'target': 'Jeden {1}', 'marks': [('1', 'code', 'w:r')]},
        {'source': '{b>Two<b}', 'target': '{b>Dwa<b}'},
        {'source': '{1>{2>N<2}<1}', 'target': '{1>{2>N<2}<1}',
         'marks': [('1', 'code', 'a'), ('2', 'code', 'b')]},
    ])
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], xlf, verbose=False)
    out = _tmp('.mxliff')
    result = merge_xliff22_to_mxliff(xlf, src, out)

    assert result['updated'] == 0
    assert result['unchanged'] == 3
    before = [_text(t.find(f'{{{NS12}}}target')) for t in _trans_units_of(src)]
    after = [_text(t.find(f'{{{NS12}}}target')) for t in _trans_units_of(out)]
    assert before == after


def test_merge_sets_confirmed_from_state():
    src = _make_mxliff([{'source': 'One', 'target': 'Jeden', 'confirmed': '0'}])
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], xlf, verbose=False)

    tree = etree.parse(str(xlf))
    seg = tree.getroot().find(f'.//{{{NS22}}}segment')
    seg.set('state', 'final')
    seg.find(f'{{{NS22}}}target').text = 'Zatwierdzone'
    tree.write(str(xlf), encoding='utf-8', xml_declaration=True)

    out = _tmp('.mxliff')
    merge_xliff22_to_mxliff(xlf, src, out)
    assert _trans_units_of(out)[0].get(f'{{{NSM}}}confirmed') == '1'


def test_merge_marks_changed_segments_as_edited():
    src = _make_mxliff([
        {'source': 'One', 'target': 'Jeden'},
        {'source': 'Two', 'target': 'Dwa'},
    ])
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], xlf, verbose=False)

    tree = etree.parse(str(xlf))
    tree.getroot().findall(f'.//{{{NS22}}}target')[0].text = 'Zmienione'
    tree.write(str(xlf), encoding='utf-8', xml_declaration=True)

    out = _tmp('.mxliff')
    merge_xliff22_to_mxliff(xlf, src, out)
    units = _trans_units_of(out)
    assert units[0].get(f'{{{NSM}}}level-edited') == 'true'
    assert units[1].get(f'{{{NSM}}}level-edited') == 'false'


def test_merge_skips_locked_segments_by_default():
    src = _make_mxliff([{'source': 'One', 'target': 'Jeden', 'locked': 'true'}])
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], xlf, verbose=False)

    tree = etree.parse(str(xlf))
    tree.getroot().find(f'.//{{{NS22}}}target').text = 'Nadpisane'
    tree.write(str(xlf), encoding='utf-8', xml_declaration=True)

    out = _tmp('.mxliff')
    result = merge_xliff22_to_mxliff(xlf, src, out)
    assert result['locked_skipped'] == 1
    assert _text(_trans_units_of(out)[0].find(f'{{{NS12}}}target')) == 'Jeden'


def test_merge_can_include_locked_segments():
    src = _make_mxliff([{'source': 'One', 'target': 'Jeden', 'locked': 'true'}])
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], xlf, verbose=False)

    tree = etree.parse(str(xlf))
    tree.getroot().find(f'.//{{{NS22}}}target').text = 'Nadpisane'
    tree.write(str(xlf), encoding='utf-8', xml_declaration=True)

    out = _tmp('.mxliff')
    merge_xliff22_to_mxliff(xlf, src, out, skip_locked=False)
    assert _text(_trans_units_of(out)[0].find(f'{{{NS12}}}target')) == 'Nadpisane'


def test_merge_keeps_inline_code_metadata_untouched():
    """
    Phrase treats m:tunit-target-metadata as a copy of m:tunit-metadata, keeping
    marks the target dropped; filtering it to the target's own codes would
    diverge from what Phrase itself writes.
    """
    src = _make_mxliff([{'source': 'A {1} B', 'target': 'A {1} B',
                         'marks': [('1', 'code', 'w:r'), ('2', 'code', 'w:t')]}])
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], xlf, verbose=False)

    tree = etree.parse(str(xlf))
    target = tree.getroot().find(f'.//{{{NS22}}}target')
    target.clear()
    target.text = 'Bez kodow'          # translator removed the code entirely
    tree.write(str(xlf), encoding='utf-8', xml_declaration=True)

    out = _tmp('.mxliff')
    merge_xliff22_to_mxliff(xlf, src, out)
    block = _trans_units_of(out)[0].find(f'{{{NSM}}}tunit-target-metadata')
    assert [m.get('id') for m in block.findall(f'{{{NSM}}}mark')] == ['1', '2']


def test_merge_reports_units_missing_from_xliff():
    src = _make_mxliff([
        {'source': 'One', 'target': 'Jeden'},
        {'source': 'Two', 'target': 'Dwa'},
    ])
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], xlf, verbose=False)

    tree = etree.parse(str(xlf))
    unit = tree.getroot().find(f'.//{{{NS22}}}unit')
    unit.getparent().remove(unit)
    tree.write(str(xlf), encoding='utf-8', xml_declaration=True)

    out = _tmp('.mxliff')
    result = merge_xliff22_to_mxliff(xlf, src, out)
    assert result['missing'] == 1


def test_merge_matches_across_joined_files():
    src = _make_mxliff(None, files=[
        ('a.docx', 'TASKA', [{'source': 'One', 'target': 'Jeden'}]),
        ('b.xml', 'TASKB', [{'source': 'Two', 'target': 'Dwa'}]),
    ])
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([src], xlf, verbose=False)

    tree = etree.parse(str(xlf))
    for i, target in enumerate(tree.getroot().findall(f'.//{{{NS22}}}target')):
        target.text = f'Nowy{i}'
    tree.write(str(xlf), encoding='utf-8', xml_declaration=True)

    out = _tmp('.mxliff')
    result = merge_xliff22_to_mxliff(xlf, src, out)
    assert result['updated'] == 2
    assert result['missing'] == 0
    assert [_text(t.find(f'{{{NS12}}}target')) for t in _trans_units_of(out)] == \
           ['Nowy0', 'Nowy1']


def test_merge_preserves_header_cdata():
    """The in-context preview skeleton is CDATA and must survive the rewrite."""
    path = _tmp('.mxliff')
    path.write_text(
        "<?xml version='1.0' encoding='UTF-8'?>"
        f'<xliff xmlns="{NS12}" xmlns:m="{NSM}" version="1.2" m:version="2.17">'
        f'<file original="d.docx" source-language="en-us" target-language="pl-pl" '
        f'm:task-id="T"><header><m:in-ctx-preview-skel bilingual="false">'
        f'<![CDATA[<html><body>x &amp; y</body></html>]]>'
        f'</m:in-ctx-preview-skel></header><body>'
        f'<group id="0"><trans-unit id="T:0" xml:space="preserve" '
        f'm:confirmed="0" m:locked="false" m:score="1.0" m:trans-origin="tm">'
        f'<source>One</source><target>Jeden</target>'
        f'</trans-unit></group></body></file></xliff>',
        encoding='utf-8',
    )
    xlf = _tmp('.xlf')
    convert_mxliff_to_xliff22([path], xlf, verbose=False)
    out = _tmp('.mxliff')
    merge_xliff22_to_mxliff(xlf, path, out)
    assert '<![CDATA[' in out.read_text(encoding='utf-8')
    assert '<html><body>x &amp; y</body></html>' in out.read_text(encoding='utf-8')
