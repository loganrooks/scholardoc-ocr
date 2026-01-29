"""Dictionary-based text quality signal using bundled word list."""

from __future__ import annotations

import re
import string
from pathlib import Path

from scholardoc_ocr.types import SignalResult

_WORDLIST_PATH = Path(__file__).parent / "data" / "wordlist.txt"

# Punctuation translation table for stripping
_PUNCT_TABLE = str.maketrans("", "", string.punctuation + "\u2013\u2014\u2018\u2019\u201c\u201d\u2026")

# Vowels for structural checks
_VOWELS = frozenset("aeiouyàáâãäåèéêëìíîïòóôõöùúûüæœ")
_CONSONANTS = frozenset("bcdfghjklmnpqrstvwxz")

# Pattern for repeated character sequences (garbled indicator)
_REPEAT_PATTERN = re.compile(r"(.)\1{3,}")
_ALTERNATING_PATTERN = re.compile(r"(..)\1{2,}")


def _load_words(path: Path) -> frozenset[str]:
    """Load word list from file, one word per line."""
    words: set[str] = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            w = line.strip()
            if w:
                words.add(w.lower())
    return frozenset(words)


def _is_structurally_valid(word: str) -> bool:
    """Check if a word has valid structure (not random character soup).

    Returns True if the word looks like it could be a real word,
    even if not in the dictionary.
    """
    lower = word.lower()
    length = len(lower)

    if length < 2:
        return True

    # Check vowel ratio
    vowel_count = sum(1 for c in lower if c in _VOWELS)
    vowel_ratio = vowel_count / length

    # Words with very few vowels are likely garbled (except short abbreviations)
    if vowel_ratio < 0.1 and length > 3:
        return False

    # Words with only vowels and length > 4 are suspicious
    if vowel_ratio > 0.9 and length > 4:
        return False

    # Check for repeated character sequences
    if _REPEAT_PATTERN.search(lower):
        return False

    # Check for alternating patterns (xzxzxz)
    if _ALTERNATING_PATTERN.search(lower):
        return False

    # Check unique chars ratio - very long words with few unique chars are garbled
    if length > 6:
        unique_ratio = len(set(lower)) / length
        if unique_ratio < 0.3:
            return False

    return True


class DictionarySignal:
    """Score text quality by checking words against a bundled word list.

    Words are classified into three categories:
    - known: found in the word list (score contribution: 1.0)
    - unknown_structured: not in list but structurally valid (score contribution: 0.5)
    - unknown_garbled: not in list and structurally invalid (score contribution: 0.0)
    """

    def __init__(self, custom_vocab_path: Path | None = None, floor: float = 0.5):
        """Initialize with bundled word list, optionally merging custom vocabulary.

        Args:
            custom_vocab_path: Optional path to additional vocabulary file (one word per line).
            floor: Minimum score threshold for the signal to pass.
        """
        words = set(_load_words(_WORDLIST_PATH))
        if custom_vocab_path is not None:
            words |= set(_load_words(custom_vocab_path))
        self._words = frozenset(words)
        self._floor = floor

    def score(self, text: str) -> SignalResult:
        """Score text based on dictionary word coverage.

        Args:
            text: The text to analyze.

        Returns:
            SignalResult with name="dictionary", score 0-1, and word count details.
        """
        if not text or not text.strip():
            return SignalResult(
                name="dictionary",
                score=1.0,
                passed=True,
                details={"known_count": 0, "unknown_structured": 0, "unknown_garbled": 0, "total": 0},
            )

        tokens = text.split()
        known_count = 0
        unknown_structured = 0
        unknown_garbled = 0
        total_scored = 0

        for token in tokens:
            # Strip punctuation
            word = token.translate(_PUNCT_TABLE).strip()

            # Skip short words and pure numbers
            if len(word) < 3 or not any(c.isalpha() for c in word):
                continue

            total_scored += 1
            lower = word.lower()

            if lower in self._words:
                known_count += 1
            elif _is_structurally_valid(word):
                unknown_structured += 1
            else:
                unknown_garbled += 1

        if total_scored == 0:
            return SignalResult(
                name="dictionary",
                score=1.0,
                passed=True,
                details={"known_count": 0, "unknown_structured": 0, "unknown_garbled": 0, "total": 0},
            )

        # Weighted score: known=1.0, structured=0.5, garbled=0.0
        weighted = known_count * 1.0 + unknown_structured * 0.5
        score = weighted / total_scored
        score = round(min(1.0, max(0.0, score)), 4)

        return SignalResult(
            name="dictionary",
            score=score,
            passed=score >= self._floor,
            details={
                "known_count": known_count,
                "unknown_structured": unknown_structured,
                "unknown_garbled": unknown_garbled,
                "total": total_scored,
            },
        )
