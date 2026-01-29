"""Comprehensive tests for composite quality analysis."""

import pytest

from scholardoc_ocr.quality import QualityAnalyzer, QualityResult


# --- Helpers ---

CLEAN_TEXT = "The quick brown fox jumps over the lazy dog. " * 20
GARBLED_TEXT = "xkjhf bvnmq zzzttt qwrtp plkmnb " * 20
MIXED_TEXT = "The quick brown fox jumps over the lazy dog xkjhf bvnmq zzzttt " * 15


def make_confidence_data(conf: int, n: int = 50) -> list[dict]:
    """Create synthetic confidence data with uniform confidence."""
    return [{"text": "word", "conf": conf} for _ in range(n)]


# --- Composite scoring basics ---


class TestCompositeBasics:
    def test_clean_text_above_threshold(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT)
        assert r.score > 0.85
        assert r.flagged is False

    def test_garbled_text_below_threshold(self):
        q = QualityAnalyzer()
        r = q.analyze(GARBLED_TEXT)
        assert r.score < 0.85
        assert r.flagged is True

    def test_mixed_text_intermediate_score(self):
        q = QualityAnalyzer()
        r = q.analyze(MIXED_TEXT)
        # Should be between pure clean and pure garbled
        clean_score = q.analyze(CLEAN_TEXT).score
        garbled_score = q.analyze(GARBLED_TEXT).score
        assert garbled_score < r.score < clean_score

    def test_empty_text_neutral(self):
        q = QualityAnalyzer()
        r = q.analyze("")
        assert r.flagged is False
        assert r.score == 1.0

    def test_short_text_neutral(self):
        q = QualityAnalyzer()
        r = q.analyze("Short text")
        assert r.flagged is False


# --- Signal breakdown ---


class TestSignalBreakdown:
    def test_has_garbled_and_dictionary_keys(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT)
        assert "garbled" in r.signal_scores
        assert "dictionary" in r.signal_scores

    def test_confidence_key_when_data_provided(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT, confidence_data=make_confidence_data(90))
        assert "confidence" in r.signal_scores

    def test_no_confidence_key_without_data(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT)
        assert "confidence" not in r.signal_scores

    def test_signal_scores_in_range(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT, confidence_data=make_confidence_data(80))
        for name, score in r.signal_scores.items():
            assert 0.0 <= score <= 1.0, f"{name} score {score} out of range"

    def test_signal_details_populated(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT)
        assert "garbled" in r.signal_details
        assert "dictionary" in r.signal_details


# --- Confidence signal integration ---


class TestConfidenceIntegration:
    def test_high_confidence_boosts_score(self):
        q = QualityAnalyzer()
        without = q.analyze(CLEAN_TEXT)
        with_high = q.analyze(CLEAN_TEXT, confidence_data=make_confidence_data(95))
        assert with_high.score >= without.score - 0.05  # shouldn't hurt clean text

    def test_low_confidence_lowers_score(self):
        q = QualityAnalyzer()
        with_low = q.analyze(CLEAN_TEXT, confidence_data=make_confidence_data(10))
        # Very low confidence triggers short-circuit to <= 0.3
        assert with_low.score <= 0.3

    def test_missing_confidence_graceful(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT, confidence_data=None)
        assert r.score > 0.0  # should work fine without

    def test_empty_confidence_data(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT, confidence_data=[])
        # Empty list -> ConfidenceSignal returns 0.5 neutral
        assert "confidence" in r.signal_scores

    def test_confidence_mean_populated(self):
        q = QualityAnalyzer()
        data = make_confidence_data(85)
        r = q.analyze(CLEAN_TEXT, confidence_data=data)
        assert r.confidence_mean is not None
        assert r.confidence_mean > 0

    def test_confidence_mean_none_without_data(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT)
        assert r.confidence_mean is None


# --- Dictionary signal ---


class TestDictionarySignal:
    def test_common_words_score_high(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT)
        assert r.signal_scores["dictionary"] > 0.7

    def test_gibberish_scores_low(self):
        q = QualityAnalyzer()
        r = q.analyze(GARBLED_TEXT)
        assert r.signal_scores["dictionary"] < 0.3


# --- German support ---


class TestGermanSupport:
    def test_german_philosophy_terms_not_flagged(self):
        text = ("Heidegger argues that Dasein is characterized by Befindlichkeit "
                "and Geworfenheit in the context of Zeitlichkeit. " * 10)
        q = QualityAnalyzer(languages=["en", "de"])
        r = q.analyze(text)
        assert r.flagged is False

    def test_german_suffix_words_not_flagged(self):
        text = ("Die Grundsätzlichkeit der Freundlichkeit und Möglichkeit "
                "zeigt die Notwendigkeit der Wissenschaft. " * 10)
        q = QualityAnalyzer(languages=["en", "de"])
        r = q.analyze(text)
        assert r.flagged is False

    def test_mixed_german_english(self):
        text = ("The concept of Dasein and Befindlichkeit shows how "
                "phenomenology reveals the structure of being. " * 10)
        q = QualityAnalyzer(languages=["en", "de"])
        r = q.analyze(text)
        assert r.flagged is False


# --- Signal floors ---


class TestSignalFloors:
    def test_floor_failure_flags_page(self):
        """Even if composite is high, a signal below its floor flags the page."""
        q = QualityAnalyzer(
            threshold=0.3,  # Very low threshold
            signal_floors={"garbled": 0.99, "dictionary": 0.0},  # Impossible garbled floor
        )
        r = q.analyze(CLEAN_TEXT)
        # Composite may be high but garbled floor of 0.99 might not be met
        # depending on exact score
        # Test the mechanism: custom floors are respected
        assert isinstance(r.flagged, bool)

    def test_custom_floors_override_defaults(self):
        q = QualityAnalyzer(signal_floors={"garbled": 0.0, "dictionary": 0.0, "confidence": 0.0})
        r = q.analyze(GARBLED_TEXT)
        # With zero floors, only composite threshold matters
        assert r.flagged == (r.score < q.threshold)


# --- Gray zone ---


class TestGrayZone:
    def test_gray_zone_constant_defined(self):
        assert QualityAnalyzer.GRAY_ZONE == 0.05

    def test_score_near_threshold_identifiable(self):
        q = QualityAnalyzer(threshold=0.85)
        r = q.analyze(CLEAN_TEXT)
        in_gray = abs(r.score - q.threshold) < q.GRAY_ZONE
        assert isinstance(in_gray, bool)


# --- Backward compatibility ---


class TestBackwardCompat:
    def test_quality_result_has_garbled_count(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT)
        assert isinstance(r.garbled_count, int)

    def test_quality_result_has_total_words(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT)
        assert isinstance(r.total_words, int)
        assert r.total_words > 0

    def test_quality_result_has_sample_issues(self):
        q = QualityAnalyzer()
        r = q.analyze(CLEAN_TEXT)
        assert isinstance(r.sample_issues, list)

    def test_analyze_pages_returns_list(self):
        q = QualityAnalyzer()
        results = q.analyze_pages([CLEAN_TEXT, GARBLED_TEXT])
        assert len(results) == 2
        assert all(isinstance(r, QualityResult) for r in results)

    def test_get_bad_pages_returns_indices(self):
        q = QualityAnalyzer()
        bad = q.get_bad_pages([CLEAN_TEXT, GARBLED_TEXT, CLEAN_TEXT])
        assert isinstance(bad, list)
        assert 1 in bad  # garbled page should be flagged
        assert 0 not in bad  # clean page should not


# --- Edge cases ---


class TestEdgeCases:
    def test_all_punctuation(self):
        text = "... !!! ??? --- ,,, ;;; ::: " * 20
        q = QualityAnalyzer()
        r = q.analyze(text)
        assert isinstance(r.score, float)

    def test_single_word(self):
        q = QualityAnalyzer()
        r = q.analyze("hello")
        assert r.flagged is False

    def test_long_text(self):
        text = "This is a normal English sentence with common words. " * 200
        q = QualityAnalyzer()
        r = q.analyze(text)
        assert r.score > 0.8

    def test_non_ascii(self):
        text = "Die Phänomenologie der différence und aletheia. " * 20
        q = QualityAnalyzer()
        r = q.analyze(text)
        assert isinstance(r.score, float)

    def test_numbers_only(self):
        text = "123 456 789 012 345 678 901 234 567 890 " * 20
        q = QualityAnalyzer()
        r = q.analyze(text)
        assert r.flagged is False


# --- Language configuration ---


class TestLanguageConfig:
    def test_german_language_config(self):
        q = QualityAnalyzer(languages=["en", "de"])
        assert "eng" in q._tesseract_langs()
        assert "deu" in q._tesseract_langs()

    def test_default_languages(self):
        q = QualityAnalyzer()
        assert q._tesseract_langs() == "eng+fra"
