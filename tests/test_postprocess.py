"""Tests for postprocess module -- all 7 POST requirements."""

from __future__ import annotations

import pytest

from scholardoc_ocr.postprocess import (
    dehyphenate,
    join_paragraphs,
    normalize_punctuation,
    normalize_unicode,
    postprocess,
)


# --- POST-01, POST-02, POST-03: normalize_unicode ---

class TestNormalizeUnicode:
    def test_nfc_normalization(self):
        # cafe with combining accent -> composed form
        assert normalize_unicode("cafe\u0301") == "caf\u00e9"

    def test_soft_hyphen_removal(self):
        assert normalize_unicode("Selbst\u00ADbewusstsein") == "Selbstbewusstsein"

    def test_ligature_fi(self):
        assert normalize_unicode("\uFB01le") == "file"

    def test_ligature_fl(self):
        assert normalize_unicode("\uFB02ow") == "flow"

    def test_ligature_ff(self):
        assert normalize_unicode("\uFB00ect") == "ffect"

    def test_ligature_ffi(self):
        assert normalize_unicode("\uFB03ce") == "ffice"

    def test_ligature_ffl(self):
        assert normalize_unicode("scu\uFB04e") == "scuffle"

    def test_all_ligatures_together(self):
        text = "\uFB00\uFB01\uFB02\uFB03\uFB04"
        assert normalize_unicode(text) == "fffiflffiffle"


# --- POST-04: join_paragraphs ---

class TestJoinParagraphs:
    def test_single_newline_joins(self):
        assert join_paragraphs("word\nword") == "word word"

    def test_double_newline_preserved(self):
        result = join_paragraphs("para1\n\nPara2")
        assert "para1" in result
        assert "Para2" in result
        assert "\n\n" in result

    def test_short_heading_not_joined(self):
        text = "Chapter One\nThis is the start of a long paragraph that continues."
        result = join_paragraphs(text)
        # Short line followed by longer content should stay separate
        assert "Chapter One" in result
        assert "Chapter One This" not in result

    def test_indented_line_starts_new_paragraph(self):
        text = "End of paragraph.\n    Indented new paragraph."
        result = join_paragraphs(text)
        assert "paragraph.    Indented" not in result
        assert "paragraph." in result


# --- POST-05, POST-06: dehyphenate ---

class TestDehyphenate:
    def test_basic_line_break_hyphen(self):
        assert "knowledge" in dehyphenate("knowl-\nedge")

    def test_german_compound_in_valid_terms(self):
        # "selbstbewusstsein" is in VALID_TERMS, so rejoin
        result = dehyphenate("Selbstbewusst-\nsein")
        assert "Selbstbewusstsein" in result

    def test_french_name_preserved(self):
        result = dehyphenate("Merleau-\nPonty")
        assert "Merleau-Ponty" in result

    def test_inline_hyphen_preserved(self):
        # Not at line break -- no change
        assert dehyphenate("well-known") == "well-known"


# --- POST-07: normalize_punctuation ---

class TestNormalizePunctuation:
    def test_space_before_period(self):
        assert normalize_punctuation("word .") == "word."

    def test_double_space_collapsed(self):
        assert normalize_punctuation("word  word") == "word word"

    def test_space_before_comma(self):
        assert normalize_punctuation("word , word") == "word, word"

    def test_trailing_whitespace_stripped(self):
        assert normalize_punctuation("hello   \n") == "hello\n"


# --- Integration: postprocess pipeline ---

class TestPostprocess:
    def test_full_pipeline(self):
        text = "The o\uFB03ce  has a \uFB01le .\nIt is well-known ."
        result = postprocess(text)
        assert "office" in result
        assert "file" in result
        assert "  " not in result
        assert " ." not in result

    def test_ligature_and_hyphen(self):
        text = "e\uFB00ort-\nlessly"
        result = postprocess(text)
        assert "effortlessly" in result
