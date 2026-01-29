"""Composite text quality analysis combining multiple signals."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from scholardoc_ocr.confidence import ConfidenceSignal
from scholardoc_ocr.dictionary import DictionarySignal
from scholardoc_ocr.types import SignalResult


@dataclass
class QualityResult:
    """Result of quality analysis."""

    score: float  # 0.0-1.0, higher is better
    flagged: bool  # True if below quality threshold
    garbled_count: int
    total_words: int
    sample_issues: list[str] = field(default_factory=list)
    sample_context: list[str] = field(default_factory=list)  # Surrounding context for issues
    # Composite fields
    signal_scores: dict[str, float] = field(default_factory=dict)
    signal_details: dict[str, dict] = field(default_factory=dict)
    confidence_mean: float | None = None
    snippets: list[str] = field(default_factory=list)


class _GarbledSignal:
    """Internal garbled-text detection signal using regex patterns.

    This contains the original QualityAnalyzer regex logic, returning a SignalResult.
    """

    # Precompiled patterns - created once at class load time
    PATTERNS = [
        (re.compile(r"[bcdfghjklmnpqrstvwxz]{6,}", re.IGNORECASE), "consonant_cluster"),
        (re.compile(r"[^\w\s\.\,\;\:\!\?\'\"\-\–\—\…\*\(\)]{3,}"), "symbol_run"),
        (re.compile(r"\b[A-Z][a-z]+[A-Z][a-z]*\b"), "weird_case"),
        (re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"), "control_char"),
    ]

    _HEIDEGGER_TERMS = frozenset({
        "erschlossenheit", "befindlichkeit", "geworfenheit", "eigentlichkeit",
        "uneigentlichkeit", "vorhandenheit", "zuhandenheit", "mitsein", "dasein",
        "zeitlichkeit", "geschichtlichkeit", "weltlichkeit", "sorge", "schuld",
        "entschlossenheit", "wiederholung", "augenblick", "vorlaufen",
        "gewesenheit", "gegenwärtigen", "gewärtigen", "verstehen", "auslegung",
        "rede", "gerede", "neugier", "zweideutigkeit", "verfallenheit",
        "angst", "furcht", "langeweile", "stimmung", "befindlich",
        "lichtung", "gestell", "ereignis", "kehre", "gelassenheit",
        "grundstimmung", "unverborgenheit", "seinsgeschichte",
    })

    _KANT_TERMS = frozenset({
        "vernunft", "verstand", "anschauung", "urteilskraft", "pflicht",
        "kategorisch", "imperativ", "transzendental", "apriorisch", "erkenntnis",
        "erscheinung", "noumenon", "ding", "einbildungskraft", "sinnlichkeit",
        "empfindung", "wahrnehmung",
    })

    _HEGEL_TERMS = frozenset({
        "geist", "aufhebung", "dialektik", "synthese", "entfremdung",
        "selbstbewusstsein", "absolut", "vermittlung", "wirklichkeit",
    })

    _HUSSERL_TERMS = frozenset({
        "intentionalität", "epoché", "reduktion", "lebenswelt",
        "noesis", "noema", "konstitution", "evidenz",
    })

    GERMAN_PHILOSOPHY_TERMS = frozenset({
        "wissenschaft", "grundlegung", "weltanschauung", "vorstellung",
        "bestimmung", "begrifflichkeit", "zusammenhang", "beziehung",
        "freiheit", "wahrheit", "sein", "seiende", "nichts", "wesen",
        "bedeutung", "sinn", "zweck", "grund", "ursache", "wirkung",
        "vorurteil", "bildung", "erfahrung", "geschichte", "natur", "kultur",
        "gesellschaft", "gemeinschaft", "freundschaft", "eigenschaft",
        "grundsätzlichkeit", "freundlichkeit", "möglichkeit", "notwendigkeit",
        "widerspruch", "gegensatz", "einheit", "vielheit", "allgemeinheit",
        "besonderheit", "einzelheit", "substanz", "subjekt", "objekt",
        "bewusstsein", "unbewusstes", "trieb", "wille", "macht",
    }) | _HEIDEGGER_TERMS | _KANT_TERMS | _HEGEL_TERMS | _HUSSERL_TERMS

    _FRENCH_TERMS = frozenset({
        "autrement", "visage", "infini", "totalité", "altérité",
        "jouissance", "fécondité", "proximité", "responsabilité",
        "substitution", "signification", "conscience", "différence",
        "présence", "absence", "parole", "écriture", "discours",
    })

    _GREEK_TERMS = frozenset({
        "aletheia", "phronesis", "episteme", "techne", "theoria", "praxis",
        "ousia", "eidos", "logos", "nous", "psyche", "pneuma",
        "arche", "telos", "dynamis", "energeia", "entelecheia",
        "eudaimonia", "arete", "sophia", "doxa", "noesis",
    })

    VALID_TERMS = GERMAN_PHILOSOPHY_TERMS | _FRENCH_TERMS | _GREEK_TERMS

    GERMAN_SUFFIXES = ("keit", "heit", "ung", "schaft", "lich", "isch", "tum", "nis")

    VALID_SHORT = frozenset({
        "a", "i", "à", "y", "ô", "le", "la", "de", "du", "un", "en",
        "et", "ou", "au", "il", "je", "tu", "on", "ce", "se", "ne",
        "the", "of", "to", "in", "is", "it", "an", "as", "at", "be",
        "by", "or", "so", "we", "if", "my", "up", "no", "do",
        "et", "in", "ad", "ex", "ab", "de",  # Latin
    })

    VALID_PATTERNS = [
        re.compile(r"^\d+$"),
        re.compile(r"^\d{1,4}[-–—]+\d{1,4}$"),
        re.compile(r"^[ivxlcdm]+$", re.IGNORECASE),
        re.compile(r"^\d{4}$"),
        re.compile(r"^[A-Z]\d+$"),
        re.compile(r"^\d+[a-z]?$"),
        re.compile(r"^ISBN", re.IGNORECASE),
        re.compile(r"^\d{1,3}\.\d"),
        re.compile(r"^[A-Z]{2,4}\d"),
        re.compile(r"^pp?\.\s*\d", re.IGNORECASE),
        re.compile(r"^\(\d+\)$"),
        re.compile(r"^\[\d+\]$"),
        re.compile(r"^§\d"),
        re.compile(r"^\d+[a-z]?[-–—]+\d+[a-z]?$"),
        re.compile(r"^[\d][\d\-–—]+[\d]$"),
        re.compile(r"^\d[\d.\-–—/]+\d$"),
    ]

    def __init__(self, threshold: float = 0.85, max_samples: int = 10):
        self.threshold = threshold
        self.max_samples = max_samples

    def score(self, text: str, collect_context: bool = False) -> SignalResult:
        """Analyze text for garbled content and return a SignalResult."""
        if not text or len(text.strip()) < 100:
            return SignalResult(
                name="garbled",
                score=1.0,
                passed=True,
                details={
                    "garbled_count": 0,
                    "total_words": 0,
                    "sample_issues": [],
                    "sample_context": [],
                },
            )

        words = text.split()
        total = len(words)
        if total == 0:
            return SignalResult(
                name="garbled",
                score=1.0,
                passed=True,
                details={
                    "garbled_count": 0,
                    "total_words": 0,
                    "sample_issues": [],
                    "sample_context": [],
                },
            )

        garbled = 0
        issues: list[str] = []
        contexts: list[str] = []

        for idx, word in enumerate(words):
            word_clean = word.strip(".,;:!?()[]{}\"'-–—")
            if len(word_clean) < 2 or word_clean.lower() in self.VALID_SHORT:
                continue

            is_valid_reference = any(p.match(word_clean) for p in self.VALID_PATTERNS)
            if is_valid_reference:
                continue

            if word_clean.lower() in self.VALID_TERMS:
                continue

            is_garbled = False
            issue_type = None

            alpha_count = sum(c.isalpha() for c in word_clean)
            if len(word_clean) > 0:
                alpha_ratio = alpha_count / len(word_clean)
                if alpha_ratio < 0.3 and len(word_clean) > 4:
                    is_garbled = True
                    issue_type = "low_alpha"

            if not is_garbled:
                has_german_suffix = word_clean.lower().endswith(self.GERMAN_SUFFIXES)
                for pattern, ptype in self.PATTERNS:
                    if ptype == "consonant_cluster" and has_german_suffix:
                        continue
                    if pattern.search(word_clean):
                        is_garbled = True
                        issue_type = ptype
                        break

            if is_garbled:
                garbled += 1
                if len(issues) < self.max_samples:
                    issues.append(f"{word_clean} ({issue_type})")

                    if collect_context:
                        start = max(0, idx - 5)
                        end = min(len(words), idx + 6)
                        context = " ".join(words[start:end])
                        contexts.append(f"...{context}...")

        ratio = garbled / total if total > 0 else 0
        score = max(0.0, 1.0 - (ratio * 2))

        return SignalResult(
            name="garbled",
            score=score,
            passed=score >= self.threshold,
            details={
                "garbled_count": garbled,
                "total_words": total,
                "sample_issues": issues,
                "sample_context": contexts if collect_context else [],
            },
        )


class QualityAnalyzer:
    """Composite quality analyzer combining garbled regex, dictionary, and confidence signals.

    Produces a weighted composite score with per-signal breakdown, gray zone detection,
    signal floor checking, and graceful handling of missing signals.
    """

    GRAY_ZONE = 0.05  # threshold +/- this defines gray zone

    def __init__(
        self,
        threshold: float = 0.85,
        max_samples: int = 10,
        signal_floors: dict[str, float] | None = None,
        languages: list[str] | None = None,
        custom_vocab_path: Path | None = None,
    ):
        self.threshold = threshold
        self.max_samples = max_samples
        self.signal_floors = signal_floors or {
            "confidence": 0.3,
            "garbled": 0.5,
            "dictionary": 0.4,
        }
        self.languages = languages or ["en", "fr"]
        self._garbled = _GarbledSignal(threshold=threshold, max_samples=max_samples)
        self._dictionary = DictionarySignal(custom_vocab_path=custom_vocab_path)
        self._confidence = ConfidenceSignal(langs=self._tesseract_langs())

    def _tesseract_langs(self) -> str:
        """Convert language codes to Tesseract format."""
        lang_map = {"en": "eng", "de": "deu", "fr": "fra", "el": "ell", "la": "lat"}
        return "+".join(lang_map.get(lang, lang) for lang in self.languages)

    def analyze(
        self,
        text: str,
        confidence_data: list[dict] | None = None,
        collect_context: bool = False,
    ) -> QualityResult:
        """Analyze text quality using composite multi-signal scoring.

        Args:
            text: The text to analyze.
            confidence_data: Optional per-word confidence data from Tesseract.
            collect_context: If True, collect surrounding words for problem areas.

        Returns:
            QualityResult with composite score and per-signal breakdown.
        """
        # Run garbled signal (always)
        garbled_result = self._garbled.score(text, collect_context)
        signals: dict[str, SignalResult] = {"garbled": garbled_result}

        # Run dictionary signal (always)
        dict_result = self._dictionary.score(text)
        signals["dictionary"] = dict_result

        # Run confidence signal (if data provided)
        if confidence_data is not None:
            conf_result = self._confidence.score_from_data(confidence_data)
            signals["confidence"] = conf_result

        # Combine signals
        composite_score = self._combine(signals)

        # Check per-signal floors
        floor_fail = any(
            s.score < self.signal_floors.get(name, 0)
            for name, s in signals.items()
        )

        # Short-circuit: very high or very low confidence
        if "confidence" in signals:
            conf_score = signals["confidence"].score
            if conf_score > 0.95:
                composite_score = max(composite_score, 0.9)
            elif conf_score < 0.2:
                composite_score = min(composite_score, 0.3)

        flagged = composite_score < self.threshold or floor_fail

        conf_details = signals.get("confidence")
        confidence_mean = conf_details.details.get("mean_conf") if conf_details else None

        return QualityResult(
            score=composite_score,
            flagged=flagged,
            garbled_count=garbled_result.details.get("garbled_count", 0),
            total_words=garbled_result.details.get("total_words", 0),
            sample_issues=garbled_result.details.get("sample_issues", []),
            sample_context=garbled_result.details.get("sample_context", []),
            signal_scores={name: s.score for name, s in signals.items()},
            signal_details={name: s.details for name, s in signals.items()},
            confidence_mean=confidence_mean,
            snippets=garbled_result.details.get("sample_issues", []),
        )

    def _combine(self, signals: dict[str, SignalResult]) -> float:
        """Compute weighted composite score from available signals."""
        if "confidence" in signals:
            weights = {"garbled": 0.4, "dictionary": 0.3, "confidence": 0.3}
        else:
            weights = {"garbled": 0.55, "dictionary": 0.45}

        total_weight = sum(weights.get(name, 0) for name in signals)
        if total_weight == 0:
            return 0.5

        return sum(
            signals[name].score * weights.get(name, 0)
            for name in signals
            if name in weights
        ) / total_weight

    def analyze_pages(
        self,
        page_texts: list[str],
        confidence_data_per_page: list[list[dict] | None] | None = None,
        collect_context: bool = False,
    ) -> list[QualityResult]:
        """Analyze quality of each page individually.

        Args:
            page_texts: List of text content for each page.
            confidence_data_per_page: Optional per-page confidence data.
            collect_context: Whether to collect context for issues.

        Returns:
            List of QualityResult, one per page.
        """
        if confidence_data_per_page is None:
            confidence_data_per_page = [None] * len(page_texts)
        return [
            self.analyze(text, conf_data, collect_context)
            for text, conf_data in zip(page_texts, confidence_data_per_page)
        ]

    def get_bad_pages(self, page_texts: list[str]) -> list[int]:
        """Get indices of pages that fail quality threshold.

        Args:
            page_texts: List of text content for each page.

        Returns:
            List of 0-indexed page numbers that need reprocessing.
        """
        results = self.analyze_pages(page_texts)
        return [i for i, r in enumerate(results) if r.flagged]
