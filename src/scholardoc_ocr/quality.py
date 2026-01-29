"""Fast text quality analysis using precompiled regex patterns."""

import re
from dataclasses import dataclass, field


@dataclass
class QualityResult:
    """Result of quality analysis."""

    score: float  # 0.0-1.0, higher is better
    flagged: bool  # True if below quality threshold
    garbled_count: int
    total_words: int
    sample_issues: list[str] = field(default_factory=list)
    sample_context: list[str] = field(default_factory=list)  # Surrounding context for issues


class QualityAnalyzer:
    """Analyze OCR text quality without subprocess calls."""

    # Precompiled patterns - created once at class load time
    # NOTE: These detect GARBLED text, but we filter out false positives below
    PATTERNS = [
        (re.compile(r"[bcdfghjklmnpqrstvwxz]{6,}", re.IGNORECASE), "consonant_cluster"),  # Raised to 6+ to allow German words
        (re.compile(r"[^\w\s\.\,\;\:\!\?\'\"\-\–\—\…\*\(\)]{3,}"), "symbol_run"),  # Exclude common punctuation
        (re.compile(r"\b[A-Z][a-z]+[A-Z][a-z]*\b"), "weird_case"),
        (re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]"), "control_char"),
    ]

    # Known philosophical/academic terms that look like garbled text but aren't
    # Covers: German (Kant, Hegel, Husserl, Heidegger), French, Greek transliterations
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
        # Common philosophical German
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

    # German compound word suffixes - words ending with these skip consonant_cluster check
    GERMAN_SUFFIXES = ("keit", "heit", "ung", "schaft", "lich", "isch", "tum", "nis")

    # Common valid short words across English/French/Latin
    VALID_SHORT = frozenset({
        "a", "i", "à", "y", "ô", "le", "la", "de", "du", "un", "en",
        "et", "ou", "au", "il", "je", "tu", "on", "ce", "se", "ne",
        "the", "of", "to", "in", "is", "it", "an", "as", "at", "be",
        "by", "or", "so", "we", "if", "my", "up", "no", "do",
        "et", "in", "ad", "ex", "ab", "de",  # Latin
    })

    # Patterns that look like legitimate references/metadata (not garbled OCR)
    VALID_PATTERNS = [
        re.compile(r"^\d+$"),  # Pure numbers (page numbers, years)
        re.compile(r"^\d{1,4}[-–—]+\d{1,4}$"),  # Page ranges: 123-456, 131—-52
        re.compile(r"^[ivxlcdm]+$", re.IGNORECASE),  # Roman numerals
        re.compile(r"^\d{4}$"),  # Years: 1987, 2024
        re.compile(r"^[A-Z]\d+$"),  # Figure refs: F1, T2
        re.compile(r"^\d+[a-z]?$"),  # Numbered items: 1, 2a, 3b
        re.compile(r"^ISBN", re.IGNORECASE),  # ISBN prefix
        re.compile(r"^\d{1,3}\.\d"),  # Decimal numbers: 3.14, 10.5
        re.compile(r"^[A-Z]{2,4}\d"),  # Codes like AE167, OB131
        re.compile(r"^pp?\.\s*\d", re.IGNORECASE),  # Page refs: p. 123, pp. 45
        re.compile(r"^\(\d+\)$"),  # Parenthetical numbers: (1), (23)
        re.compile(r"^\[\d+\]$"),  # Bracketed refs: [1], [23]
        re.compile(r"^§\d"),  # Section symbols: §44
        re.compile(r"^\d+[a-z]?[-–—]+\d+[a-z]?$"),  # Complex ranges with various dashes
        re.compile(r"^[\d][\d\-–—]+[\d]$"),  # ISBN/ID numbers with any dash type
        re.compile(r"^\d[\d.\-–—/]+\d$"),  # DOIs, dates, numeric IDs with punctuation
    ]

    def __init__(self, threshold: float = 0.85, max_samples: int = 10):
        self.threshold = threshold
        self.max_samples = max_samples

    def analyze(self, text: str, collect_context: bool = False) -> QualityResult:
        """
        Analyze text quality. Fast - no subprocesses.

        Args:
            text: The text to analyze
            collect_context: If True, collect surrounding words for problem areas (slower)
        """
        if not text or len(text.strip()) < 100:
            return QualityResult(
                score=1.0,
                flagged=False,
                garbled_count=0,
                total_words=0,
            )

        words = text.split()
        total = len(words)
        if total == 0:
            return QualityResult(
                score=1.0, flagged=False, garbled_count=0, total_words=0
            )

        garbled = 0
        issues: list[str] = []
        contexts: list[str] = []

        for idx, word in enumerate(words):
            word_clean = word.strip(".,;:!?()[]{}\"'-–—")
            if len(word_clean) < 2 or word_clean.lower() in self.VALID_SHORT:
                continue

            # Skip if it matches a valid reference/metadata pattern
            is_valid_reference = any(p.match(word_clean) for p in self.VALID_PATTERNS)
            if is_valid_reference:
                continue

            # Skip known philosophical/academic terms
            if word_clean.lower() in self.VALID_TERMS:
                continue

            is_garbled = False
            issue_type = None

            # Check alpha ratio - but be more lenient
            alpha_count = sum(c.isalpha() for c in word_clean)
            if len(word_clean) > 0:
                alpha_ratio = alpha_count / len(word_clean)
                # Only flag if VERY low alpha ratio AND not a short word
                if alpha_ratio < 0.3 and len(word_clean) > 4:
                    is_garbled = True
                    issue_type = "low_alpha"

            if not is_garbled:
                # Check garbled patterns
                # Pre-check: words with German suffixes skip consonant_cluster detection
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
                        # Get surrounding context (5 words before and after)
                        start = max(0, idx - 5)
                        end = min(len(words), idx + 6)
                        context = " ".join(words[start:end])
                        contexts.append(f"...{context}...")

        ratio = garbled / total if total > 0 else 0
        score = max(0.0, 1.0 - (ratio * 2))  # Scale: 50% garbled = 0 score

        return QualityResult(
            score=score,
            flagged=score < self.threshold,
            garbled_count=garbled,
            total_words=total,
            sample_issues=issues,
            sample_context=contexts if collect_context else [],
        )

    def analyze_pages(self, page_texts: list[str], collect_context: bool = False) -> list[QualityResult]:
        """Analyze quality of each page individually.

        Args:
            page_texts: List of text content for each page
            collect_context: Whether to collect context for issues

        Returns:
            List of QualityResult, one per page
        """
        return [self.analyze(text, collect_context) for text in page_texts]

    def get_bad_pages(self, page_texts: list[str]) -> list[int]:
        """Get indices of pages that fail quality threshold.

        Args:
            page_texts: List of text content for each page

        Returns:
            List of 0-indexed page numbers that need reprocessing
        """
        bad_pages = []
        for i, text in enumerate(page_texts):
            result = self.analyze(text, collect_context=False)
            if result.flagged:
                bad_pages.append(i)
        return bad_pages
