"""Text post-processing transforms for OCR output."""

from __future__ import annotations

import re
import unicodedata

from .quality import _GarbledSignal

# Ligature decomposition map
_LIGATURES = {
    "\uFB00": "ff",
    "\uFB01": "fi",
    "\uFB02": "fl",
    "\uFB03": "ffi",
    "\uFB04": "ffl",
}

# Known hyphenated proper names (keep hyphen even at line break)
_HYPHENATED_NAMES: frozenset[str] = frozenset({
    "merleau-ponty",
    "sartre-beauvoir",
    "buber-rosenzweig",
})

_SOFT_HYPHEN = "\u00AD"


def normalize_unicode(text: str, counts: dict | None = None) -> str:
    """NFC-normalize, decompose ligatures, remove soft hyphens."""
    total_replacements = 0
    # Decompose ligatures first (before NFC which won't touch them)
    for lig, replacement in _LIGATURES.items():
        if counts is not None:
            before_len = text.count(lig)
            total_replacements += before_len
        text = text.replace(lig, replacement)
    # Remove soft hyphens
    if counts is not None:
        total_replacements += text.count(_SOFT_HYPHEN)
    text = text.replace(_SOFT_HYPHEN, "")
    # NFC normalize
    text = unicodedata.normalize("NFC", text)
    if counts is not None:
        prev = counts.get("unicode_normalizations", 0)
        counts["unicode_normalizations"] = prev + total_replacements
    return text


def join_paragraphs(text: str, counts: dict | None = None) -> str:
    """Join single-newline lines within paragraphs, preserve paragraph boundaries."""
    join_count = 0
    # Split on double newlines to get paragraph blocks
    blocks = re.split(r"\n\n+", text)
    result_blocks = []

    for block in blocks:
        lines = block.split("\n")
        if len(lines) <= 1:
            result_blocks.append(block)
            continue

        merged_lines: list[str] = []
        for i, line in enumerate(lines):
            stripped = line.rstrip()
            # Check if this line is indented (starts new paragraph within block)
            if line and line[0] in (" ", "\t") and i > 0:
                merged_lines.append("\n" + line)
                continue
            # Check if previous line is short (heading-like): < 60 chars
            if i > 0 and merged_lines:
                prev = merged_lines[-1].rstrip()
                # If previous line is short and current starts with uppercase, keep separate
                if len(prev.replace("\n", "").strip()) < 60 and stripped and stripped[0].isupper():
                    merged_lines.append("\n" + stripped)
                    continue
            if i == 0:
                merged_lines.append(stripped)
            else:
                merged_lines.append(" " + stripped)
                if counts is not None:
                    join_count += 1

        result_blocks.append("".join(merged_lines))

    if counts is not None:
        counts["paragraph_joins"] = counts.get("paragraph_joins", 0) + join_count
    return "\n\n".join(result_blocks)


def dehyphenate(text: str, terms: frozenset[str] | None = None, counts: dict | None = None) -> str:
    """Rejoin line-break hyphens, preserve intentional hyphens."""
    if terms is None:
        terms = _GarbledSignal.VALID_TERMS

    rejoin_count = [0]  # mutable container for closure access

    def _replace_hyphen(m: re.Match) -> str:
        left = m.group(1)
        right = m.group(2)
        hyphenated = f"{left}-{right}"

        # Keep hyphen for known proper names
        if hyphenated.lower() in _HYPHENATED_NAMES:
            return hyphenated

        # Keep hyphen if both parts are capitalized (proper name heuristic)
        if left[0].isupper() and right[0].isupper():
            return hyphenated

        # Rejoin: either it's in valid terms or it's a line-break hyphen (common OCR case)
        if counts is not None:
            rejoin_count[0] += 1
        return left + right

    # Only match hyphens at line breaks
    result = re.sub(r"(\w+)-\n(\w+)", _replace_hyphen, text)
    if counts is not None:
        counts["dehyphenations"] = counts.get("dehyphenations", 0) + rejoin_count[0]
    return result


def normalize_punctuation(text: str, counts: dict | None = None) -> str:
    """Collapse whitespace around punctuation."""
    if counts is not None:
        total_fixes = 0
        # Remove space before punctuation
        text, n = re.subn(r"\s+([.,;:!?])", r"\1", text)
        total_fixes += n
        # Collapse multiple spaces
        text, n = re.subn(r"  +", " ", text)
        total_fixes += n
        # Strip trailing whitespace per line
        text, n = re.subn(r"[ \t]+(\n)", r"\1", text)
        total_fixes += n
        text, n = re.subn(r"[ \t]+$", "", text)
        total_fixes += n
        counts["punctuation_fixes"] = counts.get("punctuation_fixes", 0) + total_fixes
    else:
        # Remove space before punctuation
        text = re.sub(r"\s+([.,;:!?])", r"\1", text)
        # Collapse multiple spaces
        text = re.sub(r"  +", " ", text)
        # Strip trailing whitespace per line
        text = re.sub(r"[ \t]+(\n)", r"\1", text)
        text = re.sub(r"[ \t]+$", "", text)
    return text


def postprocess(text: str, counts: dict | None = None) -> str:
    """Chain all transforms: unicode -> paragraphs -> dehyphenate -> punctuation."""
    text = normalize_unicode(text, counts=counts)
    text = dehyphenate(text, counts=counts)
    text = join_paragraphs(text, counts=counts)
    text = normalize_punctuation(text, counts=counts)
    return text
