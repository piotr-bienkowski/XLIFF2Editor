import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from Xedaibt import _filter_matches


def test_no_filter_always_visible():
    assert _filter_matches("hello", "world", None, None, True) is True


def test_source_plain_match():
    assert _filter_matches("Hello World", "anything", "hello", None, True) is True


def test_source_plain_case_insensitive():
    assert _filter_matches("HELLO WORLD", "anything", "hello", None, True) is True


def test_source_plain_no_match():
    assert _filter_matches("Hello World", "anything", "xyz", None, True) is False


def test_target_plain_match():
    assert _filter_matches("anything", "Cześć świat", None, "cześć", True) is True


def test_target_plain_no_match():
    assert _filter_matches("anything", "Cześć świat", None, "xyz", True) is False


def test_both_and_both_match():
    assert _filter_matches("Hello", "Cześć", "hello", "cześć", True) is True


def test_both_and_only_source_matches():
    assert _filter_matches("Hello", "Cześć", "hello", "xyz", True) is False


def test_both_or_only_source_matches():
    assert _filter_matches("Hello", "Cześć", "hello", "xyz", False) is True


def test_both_or_neither_matches():
    assert _filter_matches("Hello", "Cześć", "xyz", "abc", False) is False


def test_regex_source_match():
    pat = re.compile(r"hel+o", re.IGNORECASE)
    assert _filter_matches("Hello World", "anything", pat, None, True) is True


def test_regex_source_no_match():
    pat = re.compile(r"^World", re.IGNORECASE)
    assert _filter_matches("Hello World", "anything", pat, None, True) is False


def test_regex_target_match():
    pat = re.compile(r"\d+", re.IGNORECASE)
    assert _filter_matches("anything", "segment 42", None, pat, True) is True
