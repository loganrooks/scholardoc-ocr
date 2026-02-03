"""Text post-processing transforms for OCR output."""

from __future__ import annotations


def normalize_unicode(text: str) -> str:
    """NFC-normalize, decompose ligatures, remove soft hyphens."""
    return ""


def join_paragraphs(text: str) -> str:
    """Join single-newline lines within paragraphs, preserve paragraph boundaries."""
    return ""


def dehyphenate(text: str, terms: frozenset[str] | None = None) -> str:
    """Rejoin line-break hyphens, preserve intentional hyphens."""
    return ""


def normalize_punctuation(text: str) -> str:
    """Collapse whitespace around punctuation."""
    return ""


def postprocess(text: str) -> str:
    """Chain all transforms."""
    return ""
