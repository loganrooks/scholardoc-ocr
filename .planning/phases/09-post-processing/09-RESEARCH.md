# Phase 9: Post-Processing - Research

**Researched:** 2026-02-02
**Domain:** Text normalization / OCR post-processing
**Confidence:** HIGH

## Summary

Phase 9 is pure text transformation using Python stdlib. The requirements (Unicode NFC, ligature decomposition, soft hyphen removal, paragraph joining, dehyphenation, punctuation normalization) are all achievable with `unicodedata` and `re` from the standard library. No external libraries are needed.

The key challenge is POST-06 (language-aware dehyphenation) -- distinguishing line-break hyphens from intentional German compounds and French hyphenated names. The codebase already has extensive German/French term whitelists in `quality.py`'s `_GarbledSignal` class that should be reused.

**Primary recommendation:** Create a single `src/scholardoc_ocr/postprocess.py` module with a pipeline of composable transform functions, each handling one requirement. Integrate it at the point where text is extracted/returned in `pipeline.py`.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `unicodedata` (stdlib) | N/A | NFC normalization, character categories | Built-in, authoritative Unicode support |
| `re` (stdlib) | N/A | Pattern matching for dehyphenation, punctuation | Already used throughout codebase |

### Supporting
No external libraries needed. This is entirely stdlib work.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual ligature map | `unidecode` | Overkill -- only 5 ligatures needed (fi, fl, ff, ffi, ffl). A dict is cleaner and more predictable for academic text |
| Regex dehyphenation | `pyphen` (hyphenation library) | Could improve dehyphenation accuracy but adds a dependency for marginal benefit; regex + whitelist is sufficient |

## Architecture Patterns

### Recommended Project Structure
```
src/scholardoc_ocr/
├── postprocess.py       # All transforms: normalize(), dehyphenate(), clean()
├── quality.py           # Existing -- reuse VALID_TERMS for dehyphenation
└── pipeline.py          # Call postprocess after text extraction
```

### Pattern 1: Transform Pipeline
**What:** Chain of pure functions, each handling one concern
**When to use:** Always -- this is the core pattern

```python
def postprocess(text: str, terms: frozenset[str] | None = None) -> str:
    """Apply all post-processing transforms in order."""
    text = normalize_unicode(text)      # POST-01, POST-02, POST-03
    text = join_paragraphs(text)        # POST-04
    text = dehyphenate(text, terms)     # POST-05, POST-06
    text = normalize_punctuation(text)  # POST-07
    return text
```

### Pattern 2: Reuse Existing Term Whitelists
**What:** Import `_GarbledSignal.VALID_TERMS` (or refactor to a shared location) for dehyphenation
**When to use:** POST-06 -- the same German/French terms that quality.py whitelists are the ones that should keep their hyphens

### Anti-Patterns to Avoid
- **Monolithic function:** Don't put all transforms in one giant regex or function. Each requirement = one function.
- **Destroying paragraph boundaries:** The naive approach of replacing all `\n` with spaces destroys structure. Must detect paragraph boundaries (double newline, indentation change) and preserve them.
- **Greedy dehyphenation:** Don't blindly rejoin all `word-\nword` patterns. German compounds like "Selbst-bewusstsein" may appear hyphenated at line breaks AND be intentional compounds.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Unicode normalization | Custom char mapping | `unicodedata.normalize('NFC', text)` | Stdlib handles all edge cases correctly |
| Character category checks | Regex for "is this a letter" | `unicodedata.category(char)` | Handles all Unicode scripts |

## Common Pitfalls

### Pitfall 1: Ligature Map Incompleteness
**What goes wrong:** Missing ligatures like U+FB01 (fi), U+FB02 (fl), U+FB00 (ff), U+FB03 (ffi), U+FB04 (ffl)
**Why it happens:** Tesseract and Surya may output different ligature forms
**How to avoid:** Explicit dict mapping all 5 standard Latin ligatures. Also handle U+0132 (IJ), U+0133 (ij) for completeness.
**Warning signs:** Words like "fficacy" or "flter" in output (ligature stripped wrong)

### Pitfall 2: Paragraph Detection False Positives
**What goes wrong:** Short lines (headings, citations, list items) misidentified as wrapped paragraphs
**Why it happens:** Line length alone doesn't distinguish wrapped text from intentional short lines
**How to avoid:** Use multiple signals: double newline = paragraph break; single newline with following indentation = paragraph break; single newline where previous line is short (< ~60 chars) = likely paragraph break, not wrap.
**Warning signs:** Headings merged into following paragraphs

### Pitfall 3: Dehyphenation Destroying German Compounds
**What goes wrong:** "Selbst-\nbewusstsein" rejoined as "Selbstbewusstsein" (correct) but "Merleau-\nPonty" also rejoined as "MerleauPonty" (wrong)
**Why it happens:** Naive pattern `word-\nword` matches both cases
**How to avoid:** Rules: (1) If the full joined word is in VALID_TERMS, rejoin. (2) If either part is capitalized (proper noun pattern like "Merleau-Ponty"), keep hyphen. (3) If neither part alone is a common word, keep hyphen (conservative default).
**Warning signs:** French names losing hyphens

### Pitfall 4: NFC vs NFKC
**What goes wrong:** Using NFKC instead of NFC destroys semantic distinctions (e.g., superscripts become regular chars)
**Why it happens:** NFKC is "more aggressive" normalization
**How to avoid:** Use NFC. Handle ligatures separately with explicit mapping rather than relying on NFKC compatibility decomposition.

### Pitfall 5: Soft Hyphen vs Regular Hyphen
**What goes wrong:** Stripping U+002D (regular hyphen-minus) instead of U+00AD (soft hyphen)
**Why it happens:** Copy-paste errors in character codes
**How to avoid:** Be explicit: `text.replace('\u00ad', '')`. Test with actual soft hyphens.

## Code Examples

### Unicode Normalization (POST-01, POST-02, POST-03)
```python
import unicodedata

LIGATURE_MAP = {
    '\ufb00': 'ff',
    '\ufb01': 'fi',
    '\ufb02': 'fl',
    '\ufb03': 'ffi',
    '\ufb04': 'ffl',
}

def normalize_unicode(text: str) -> str:
    """NFC normalize, strip soft hyphens, decompose ligatures."""
    # Decompose ligatures first (before NFC which might recompose)
    for lig, replacement in LIGATURE_MAP.items():
        text = text.replace(lig, replacement)
    # Strip soft hyphens
    text = text.replace('\u00ad', '')
    # NFC normalize
    text = unicodedata.normalize('NFC', text)
    return text
```

### Paragraph Joining (POST-04)
```python
import re

def join_paragraphs(text: str) -> str:
    """Join lines within paragraphs; preserve paragraph boundaries."""
    # Preserve double+ newlines as paragraph separators
    # Split into paragraphs first
    paragraphs = re.split(r'\n\s*\n', text)
    result = []
    for para in paragraphs:
        # Within a paragraph, join lines
        lines = para.split('\n')
        joined = ' '.join(line.strip() for line in lines if line.strip())
        result.append(joined)
    return '\n\n'.join(result)
```

### Dehyphenation (POST-05, POST-06)
```python
import re

# Pattern: word ending with hyphen at end of line, continued on next line
HYPHEN_PATTERN = re.compile(r'(\w+)-\s*\n\s*(\w+)')

def dehyphenate(text: str, known_terms: frozenset[str] | None = None) -> str:
    """Rejoin hyphenated line breaks, preserving intentional hyphens."""
    known_terms = known_terms or frozenset()

    def _should_rejoin(match: re.Match) -> str:
        left, right = match.group(1), match.group(2)
        joined = left + right

        # If joined form is a known term, rejoin
        if joined.lower() in known_terms:
            return joined

        # If both parts capitalized (proper name like Merleau-Ponty), keep hyphen
        if left[0].isupper() and right[0].isupper():
            return f'{left}-{right}'

        # Default: rejoin (most line-break hyphens are artifacts)
        return joined

    return HYPHEN_PATTERN.sub(_should_rejoin, text)
```

### Punctuation Normalization (POST-07)
```python
import re

def normalize_punctuation(text: str) -> str:
    """Collapse extra whitespace around punctuation."""
    # Remove space before punctuation
    text = re.sub(r'\s+([.,;:!?)])', r'\1', text)
    # Ensure space after punctuation (except before closing)
    text = re.sub(r'([.,;:!?])(\w)', r'\1 \2', text)
    # Collapse multiple spaces
    text = re.sub(r'  +', ' ', text)
    return text
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| NFKC for everything | NFC + explicit ligature map | Best practice | Preserves semantic distinctions |
| Blind dehyphenation | Language-aware with term lists | N/A | Prevents destroying compound words |

## Open Questions

1. **Where exactly to integrate in pipeline**
   - What we know: Text is extracted via `PDFProcessor.extract_text()` and written to `.txt` files
   - What's unclear: Exact point in `pipeline.py` where text output is finalized
   - Recommendation: Read full pipeline.py during planning to identify integration point

2. **French punctuation spacing**
   - What we know: French uses spaces before `;:!?` (e.g., "mot ; mot")
   - What's unclear: Whether to preserve French spacing or normalize to English rules
   - Recommendation: Since output is RAG-ready, normalize to English (no space before punctuation) -- RAG tokenizers handle this better

## Sources

### Primary (HIGH confidence)
- Python `unicodedata` module documentation -- stdlib, well-known API
- Existing codebase `quality.py` -- term whitelists already implemented

### Secondary (MEDIUM confidence)
- OCR post-processing patterns from training data -- common, well-established techniques

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - stdlib only, well-known APIs
- Architecture: HIGH - simple transform pipeline, clear pattern
- Pitfalls: HIGH - well-known OCR post-processing challenges
- Dehyphenation logic: MEDIUM - heuristics may need tuning with real data

**Research date:** 2026-02-02
**Valid until:** 2026-06-01 (stable domain, stdlib)
