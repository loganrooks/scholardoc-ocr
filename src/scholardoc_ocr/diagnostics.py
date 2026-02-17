"""Diagnostic data model for per-page pipeline instrumentation.

Contains dataclasses for structured diagnostic data (SignalDisagreement,
EngineDiff, PageDiagnostics) and utility functions for signal disagreement
detection, struggle classification, engine diffing, and building diagnostics
from QualityResult objects.

All dataclasses use only primitive types (float, int, str, bool, list, dict, None)
to ensure safe pickling through ProcessPoolExecutor.
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from itertools import combinations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scholardoc_ocr.quality import QualityResult

# Default threshold for flagging signal disagreement (DIAG-03).
# Pairs with magnitude above this are flagged via has_signal_disagreement.
# Phase 19 can recalibrate without schema changes.
DISAGREEMENT_THRESHOLD = 0.3


@dataclass
class SignalDisagreement:
    """A pair of quality signals and their pairwise disagreement magnitude."""

    signals: list[str]  # e.g. ["garbled", "confidence"]
    magnitude: float  # absolute difference between signal scores


@dataclass
class EngineDiff:
    """Structured word-level diff between Tesseract and Surya output."""

    additions: list[str]  # words Surya added
    deletions: list[str]  # words Surya removed
    substitutions: list[dict[str, str]]  # [{"old": "teh", "new": "the"}, ...]
    summary: dict[str, int]  # {"additions": N, "deletions": N, "substitutions": N}

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary."""
        return {
            "additions": self.additions,
            "deletions": self.deletions,
            "substitutions": self.substitutions,
            "summary": self.summary,
        }


@dataclass
class PageDiagnostics:
    """Per-page diagnostic data attached to PageResult.

    Always-captured fields (near-zero marginal cost) are non-optional.
    Diagnostics-gated fields (meaningful cost, require --diagnostics) default to None.
    """

    # DIAG-02: Signal breakdown (always captured)
    signal_scores: dict[str, float] = field(default_factory=dict)
    signal_details: dict[str, dict] = field(default_factory=dict)
    composite_weights: dict[str, float] = field(default_factory=dict)

    # DIAG-03: Signal disagreement (always captured)
    signal_disagreements: list[SignalDisagreement] = field(default_factory=list)
    has_signal_disagreement: bool = False

    # DIAG-05: Postprocess counts (always captured, filled by postprocess wiring)
    postprocess_counts: dict[str, int] = field(default_factory=dict)

    # DIAG-06: Struggle categories (always captured)
    struggle_categories: list[str] = field(default_factory=list)

    # DIAG-01: Image quality (--diagnostics only)
    image_quality: dict[str, float | None] | None = None

    # DIAG-04: Engine comparison (--diagnostics only)
    tesseract_text: str | None = None
    engine_diff: EngineDiff | None = None

    def to_dict(self) -> dict:
        """Convert to a JSON-serializable dictionary.

        Diagnostics-gated fields are only included when non-None.
        """
        d: dict = {
            "signal_scores": self.signal_scores,
            "signal_details": self.signal_details,
            "composite_weights": self.composite_weights,
            "signal_disagreements": [
                {"signals": sd.signals, "magnitude": sd.magnitude}
                for sd in self.signal_disagreements
            ],
            "has_signal_disagreement": self.has_signal_disagreement,
            "postprocess_counts": self.postprocess_counts,
            "struggle_categories": self.struggle_categories,
        }
        if self.image_quality is not None:
            d["image_quality"] = self.image_quality
        if self.tesseract_text is not None:
            d["tesseract_text"] = self.tesseract_text
        if self.engine_diff is not None:
            d["engine_diff"] = self.engine_diff.to_dict()
        return d


def compute_signal_disagreements(
    signal_scores: dict[str, float],
) -> list[SignalDisagreement]:
    """Compute pairwise signal disagreement magnitudes.

    Returns all pairs (not just those above threshold) so downstream
    consumers can apply their own thresholds. Magnitude rounded to 4 decimals.

    Args:
        signal_scores: Signal name to score mapping (e.g. {"garbled": 0.9, "dictionary": 0.8}).

    Returns:
        List of SignalDisagreement for each pair of signals.
    """
    disagreements = []
    for (name_a, score_a), (name_b, score_b) in combinations(signal_scores.items(), 2):
        magnitude = round(abs(score_a - score_b), 4)
        disagreements.append(SignalDisagreement(signals=[name_a, name_b], magnitude=magnitude))
    return disagreements


def classify_struggle(
    signal_scores: dict[str, float],
    composite_score: float,
    threshold: float,
    image_quality: dict[str, float | None] | None = None,
    engine: str | None = None,
    surya_score: float | None = None,
) -> list[str]:
    """Assign all applicable struggle categories to a page.

    Each category has an independent boolean detection rule. All 8 checks
    run independently; the returned list contains every category that fires.
    Thresholds are conservative, erring toward under-reporting. Phase 19
    will calibrate using ground truth data.

    Categories:
        bad_scan: Image quality metrics indicate poor input scan.
        character_confusion: Characters recognized but wrong (e.g. 'rn' -> 'm').
        vocabulary_miss: Characters correct but words not in dictionary.
        layout_error: High confidence but low composite (layout issues).
        language_confusion: Dictionary very low with moderate garbled.
        signal_disagreement: Quality signals diverge significantly.
        gray_zone: Score near threshold boundary.
        surya_insufficient: Page went through Surya but still flagged.

    Args:
        signal_scores: Signal name to score mapping.
        composite_score: Overall composite quality score.
        threshold: Quality threshold for flagging.
        image_quality: Optional image quality metrics (from --diagnostics).
        engine: OCR engine used ("tesseract" or "surya").
        surya_score: Quality score after Surya processing (if applicable).

    Returns:
        List of applicable struggle category strings. May be empty.
    """
    categories: list[str] = []

    garbled = signal_scores.get("garbled", 1.0)
    dictionary = signal_scores.get("dictionary", 1.0)
    confidence = signal_scores.get("confidence")

    # bad_scan: image quality metrics indicate poor input
    # Strong signal when image_quality available (--diagnostics)
    # Fallback: very low confidence + very low garbled suggests unreadable input
    if image_quality:
        if image_quality.get("blur_score", 999) < 50 or image_quality.get("contrast", 1.0) < 0.1:
            categories.append("bad_scan")
    elif confidence is not None and confidence < 0.3 and garbled < 0.4:
        categories.append("bad_scan")

    # character_confusion: garbled score low but dictionary score decent
    # Suggests characters recognized but wrong (e.g., 'rn' -> 'm')
    if garbled < 0.7 and dictionary > 0.5:
        categories.append("character_confusion")

    # vocabulary_miss: dictionary score low but garbled score decent
    # Suggests characters correct but words not in dictionary (foreign terms, jargon)
    if dictionary < 0.6 and garbled > 0.7:
        categories.append("vocabulary_miss")

    # layout_error: heuristic -- high confidence but low composite
    # Weak signal coverage (CONTEXT.md notes this)
    if confidence is not None and confidence > 0.7 and composite_score < threshold:
        categories.append("layout_error")

    # language_confusion: heuristic -- dictionary very low, garbled moderate
    # Weak signal coverage
    if dictionary < 0.4 and 0.4 < garbled < 0.7:
        categories.append("language_confusion")

    # signal_disagreement: signals diverge significantly
    if confidence is not None:
        pairs = [
            abs(garbled - confidence),
            abs(garbled - dictionary),
            abs(dictionary - confidence),
        ]
        if any(p > DISAGREEMENT_THRESHOLD for p in pairs):
            categories.append("signal_disagreement")
    elif abs(garbled - dictionary) > DISAGREEMENT_THRESHOLD:
        categories.append("signal_disagreement")

    # gray_zone: score near threshold boundary
    if abs(composite_score - threshold) < 0.05:
        categories.append("gray_zone")

    # surya_insufficient: page went through Surya but still flagged
    if engine == "surya" and surya_score is not None and surya_score < threshold:
        categories.append("surya_insufficient")

    return categories


def compute_engine_diff(tesseract_text: str, surya_text: str) -> EngineDiff:
    """Compute structured word-level diff between engine outputs.

    Uses difflib.SequenceMatcher on word-split texts to identify additions
    (words Surya added), deletions (words Surya removed), and substitutions
    (word spans that changed between engines).

    Args:
        tesseract_text: Text output from Tesseract OCR.
        surya_text: Text output from Surya OCR.

    Returns:
        EngineDiff with additions, deletions, substitutions, and summary counts.
    """
    words_a = tesseract_text.split()
    words_b = surya_text.split()

    sm = difflib.SequenceMatcher(None, words_a, words_b)

    additions: list[str] = []
    deletions: list[str] = []
    substitutions: list[dict[str, str]] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            additions.extend(words_b[j1:j2])
        elif tag == "delete":
            deletions.extend(words_a[i1:i2])
        elif tag == "replace":
            substitutions.append(
                {
                    "old": " ".join(words_a[i1:i2]),
                    "new": " ".join(words_b[j1:j2]),
                }
            )

    return EngineDiff(
        additions=additions,
        deletions=deletions,
        substitutions=substitutions,
        summary={
            "additions": len(additions),
            "deletions": len(deletions),
            "substitutions": len(substitutions),
        },
    )


def build_always_diagnostics(qr: QualityResult, threshold: float) -> PageDiagnostics:
    """Build always-captured diagnostics from an existing QualityResult.

    Extracts signal scores, signal details, and composite weights from the
    QualityResult (which already computes this data during quality analysis).
    Computes signal disagreements and struggle categories. Leaves postprocess_counts
    empty (filled later by postprocess wiring) and diagnostics-gated fields as None.

    Args:
        qr: QualityResult from quality.py's QualityAnalyzer.analyze().
        threshold: Quality threshold for flagging (used by struggle classification).

    Returns:
        PageDiagnostics with always-captured fields populated.
    """
    signal_scores = dict(qr.signal_scores)
    signal_details = dict(qr.signal_details)

    # Determine which weight set was used based on available signals
    if "confidence" in signal_scores:
        weights = {"garbled": 0.4, "dictionary": 0.3, "confidence": 0.3}
    else:
        weights = {"garbled": 0.55, "dictionary": 0.45}

    # DIAG-03: Signal disagreement
    disagreements = compute_signal_disagreements(signal_scores)
    has_disagreement = any(d.magnitude > DISAGREEMENT_THRESHOLD for d in disagreements)

    # DIAG-06: Struggle categories
    categories = classify_struggle(signal_scores, qr.score, threshold)

    return PageDiagnostics(
        signal_scores=signal_scores,
        signal_details=signal_details,
        composite_weights=weights,
        signal_disagreements=disagreements,
        has_signal_disagreement=has_disagreement,
        postprocess_counts={},
        struggle_categories=categories,
    )
