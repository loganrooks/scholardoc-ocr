# Phase 2: Quality Analysis Enhancement - Research

**Researched:** 2026-01-29
**Domain:** OCR quality scoring, hOCR confidence extraction, multi-signal text analysis
**Confidence:** HIGH

## Summary

This phase replaces the existing regex-only `QualityAnalyzer` with a composite scoring system that combines four signals: Tesseract word-level confidence (from hOCR), garbled text regex (existing), dictionary validation, and layout checks. It also adds German language support.

The current `quality.py` is a single class (`QualityAnalyzer`) with one method (`analyze`) that counts garbled words via regex patterns and whitelists. The new system needs to produce a composite 0-1 score from multiple signals while keeping the same interface contract: the pipeline calls `analyze()` or `analyze_pages()` and gets results with `score` and `flagged` fields.

The key technical challenge is obtaining Tesseract word-level confidence. ocrmypdf does NOT expose per-word confidence scores. The two viable approaches are: (1) use `pytesseract.image_to_data()` which returns confidence per word directly, requiring PDF-to-image conversion via PyMuPDF (already a dependency); or (2) run Tesseract with hOCR output and parse `x_wconf` attributes. Approach (1) is simpler and avoids HTML parsing. PyMuPDF can render pages to pixmaps natively, avoiding a `pdf2image`/`poppler` dependency.

**Primary recommendation:** Use `pytesseract.image_to_data()` with PyMuPDF page-to-pixmap rendering for confidence extraction. Keep the existing regex signals. Add a simple bundled word frequency list for dictionary validation. Refactor `QualityResult` to include per-signal breakdown.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytesseract | >=0.3.10 | Word-level confidence via `image_to_data()` | Only Python API exposing Tesseract confidence per word; returns structured dict with `conf`, `text`, `left`, `top`, etc. |
| pymupdf (fitz) | >=1.24.0 (already dep) | PDF page to image conversion | Already in project. `page.get_pixmap()` returns PIL-compatible image without poppler dependency |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| beautifulsoup4 + lxml | latest | hOCR parsing | Only if pytesseract approach proves insufficient; NOT recommended as primary path |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytesseract `image_to_data` | Direct Tesseract CLI + hOCR parsing | More complex, requires BS4/lxml, but gives richer layout info (bounding boxes, paragraphs) |
| pytesseract `image_to_data` | ocrmypdf sidecar + hOCR renderer internal | Undocumented internal API, fragile across versions |
| Bundled word list | pyspellchecker / hunspell | External dependency; pyspellchecker pulls large dictionaries; context says "no external spellcheck dependency" |

**Installation:**
```bash
pip install pytesseract
```

Note: Tesseract binary must already be installed (it is, since ocrmypdf depends on it).

## Architecture Patterns

### Recommended Module Structure
```
src/scholardoc_ocr/
├── quality.py           # Refactored: CompositeQualityAnalyzer + signal classes
├── confidence.py        # NEW: Tesseract confidence extraction via pytesseract
├── dictionary.py        # NEW: Dictionary validation signal (bundled word list)
├── data/                # NEW: Bundled resources
│   └── wordlist.txt     # Frequency-based word list (English + academic terms)
└── ...existing files...
```

### Pattern 1: Signal-Based Composite Scoring
**What:** Each quality signal is a function/class that takes page text (or OCR data) and returns a 0-1 score. A compositor combines them.
**When to use:** When combining independent quality metrics.
**Example:**
```python
@dataclass
class SignalResult:
    name: str
    score: float  # 0-1
    passed: bool  # Above per-signal floor
    details: dict  # Signal-specific breakdown

@dataclass
class CompositeQualityResult:
    score: float  # Combined 0-1
    flagged: bool
    signals: list[SignalResult]
    snippets: list[str]  # Problematic text samples

class CompositeQualityAnalyzer:
    def __init__(self, threshold=0.85, signal_floors=None):
        self.threshold = threshold
        self.signal_floors = signal_floors or {
            "confidence": 0.3,
            "garbled": 0.5,
        }

    def analyze_page(self, text, confidence_data=None) -> CompositeQualityResult:
        signals = []
        signals.append(self._garbled_signal(text))
        signals.append(self._dictionary_signal(text))
        if confidence_data:
            signals.append(self._confidence_signal(confidence_data))

        composite = self._combine(signals)
        # Check per-signal floors
        floor_fail = any(
            s.score < self.signal_floors.get(s.name, 0)
            for s in signals
        )
        flagged = composite < self.threshold or floor_fail
        return CompositeQualityResult(score=composite, flagged=flagged, signals=signals, snippets=[])
```

### Pattern 2: Confidence Extraction Pipeline
**What:** Convert PDF page to image via PyMuPDF, run pytesseract.image_to_data, extract confidence.
**When to use:** When Tesseract confidence signal is needed.
**Example:**
```python
import fitz
import pytesseract
from PIL import Image
import io

def extract_page_confidence(pdf_path: Path, page_num: int, langs: str = "eng+fra") -> list[dict]:
    """Extract word-level confidence from a PDF page."""
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    # Render at 300 DPI for good OCR
    pix = page.get_pixmap(dpi=300)
    img = Image.open(io.BytesIO(pix.tobytes("png")))

    data = pytesseract.image_to_data(img, lang=langs, output_type=pytesseract.Output.DICT)
    words = []
    for i in range(len(data["text"])):
        if data["text"][i].strip():
            words.append({
                "text": data["text"][i],
                "conf": data["conf"][i],  # 0-100, -1 for non-text
            })
    doc.close()
    return words
```

### Pattern 3: Gray Zone Handling
**What:** Pages near the threshold get additional analysis before final flag/pass decision.
**When to use:** Borderline scores where a second look prevents false positives/negatives.
**Example:**
```python
GRAY_ZONE = 0.05  # threshold +/- this value

def is_gray_zone(score, threshold):
    return abs(score - threshold) < GRAY_ZONE

# Gray zone strategy: run all signals at higher scrutiny
# e.g., if initial score used only fast signals, run dictionary signal too
```

### Anti-Patterns to Avoid
- **Running pytesseract on every page unconditionally:** Rendering pages to images at 300 DPI is slow. Only run confidence extraction when the fast regex signal is ambiguous (gray zone) or as a parallel signal during Tesseract OCR phase.
- **Using pandas for image_to_data:** pytesseract can return a DataFrame but the dict output is sufficient and avoids the pandas dependency.
- **Global word list loading:** Load the bundled word list once at analyzer init, not per-page.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Word-level OCR confidence | Custom Tesseract output parser | `pytesseract.image_to_data()` | Handles all Tesseract output formats, well-tested |
| PDF page to image | pdf2image + poppler | `fitz.Page.get_pixmap()` | PyMuPDF already a dependency, no poppler needed |
| hOCR XML parsing (if needed) | Manual regex on HTML | `BeautifulSoup` with lxml | hOCR has nested structures, regex breaks on edge cases |
| German compound detection | Custom morphological analyzer | Simple prefix/suffix stripping + dictionary lookup | Full morphological analysis is a PhD project; heuristic is sufficient |

**Key insight:** The confidence extraction is the only truly new capability needed. The existing regex garbled detection is solid. The dictionary signal can be a simple set lookup. Don't over-engineer any single signal.

## Common Pitfalls

### Pitfall 1: pytesseract Confidence Returns -1 for Non-Text Elements
**What goes wrong:** `image_to_data` returns `conf=-1` for empty/whitespace entries. Including these in averages tanks the score.
**Why it happens:** Tesseract outputs entries for every detected region, including empty ones.
**How to avoid:** Filter `conf > 0 and text.strip() != ""` before aggregating.
**Warning signs:** Unexpectedly low confidence scores on clean pages.

### Pitfall 2: DPI Matters for Confidence Quality
**What goes wrong:** Low-resolution rendering produces worse OCR and lower confidence, even on clean text.
**Why it happens:** Tesseract expects ~300 DPI input.
**How to avoid:** Always render at 300 DPI: `page.get_pixmap(dpi=300)`.
**Warning signs:** Confidence scores much lower than expected on known-good pages.

### Pitfall 3: Confidence Signal Unavailable for Pre-OCR'd PDFs
**What goes wrong:** If the pipeline path is "existing text is good enough," there's no Tesseract confidence data because Tesseract wasn't run.
**Why it happens:** The "existing" path extracts text via PyMuPDF, not Tesseract.
**How to avoid:** Treat confidence as an optional signal. When unavailable, composite score uses remaining signals with reweighted combination. Design the compositor to handle missing signals gracefully.
**Warning signs:** Code assumes confidence is always present.

### Pitfall 4: German Compound Words Trigger Garbled Detection
**What goes wrong:** Long German compounds like "Grundlegungswissenschaft" (23 chars) with consonant clusters trigger the garbled regex.
**Why it happens:** Current consonant cluster pattern flags 6+ consecutive consonants. German routinely produces these.
**How to avoid:** When German is enabled, either relax the consonant cluster threshold or add a German compound decomposition heuristic (split on common suffixes: -keit, -heit, -ung, -schaft, -lich, etc. and check parts).
**Warning signs:** High garbled counts on known-good German text.

### Pitfall 5: Performance Regression from Confidence Extraction
**What goes wrong:** Running pytesseract on every page adds significant latency (page render + OCR = seconds per page).
**Why it happens:** 300 DPI rendering + Tesseract re-run is expensive.
**How to avoid:** Only extract confidence when: (a) page is in gray zone on fast signals, or (b) during the Tesseract phase where we already have the data. For the "existing text" path, skip confidence entirely.
**Warning signs:** Pipeline runtime doubles or more.

## Code Examples

### PyMuPDF Page to PIL Image (No External Deps)
```python
# Source: PyMuPDF documentation
import fitz
from PIL import Image
import io

doc = fitz.open("document.pdf")
page = doc[0]
pix = page.get_pixmap(dpi=300)
img = Image.open(io.BytesIO(pix.tobytes("png")))
# img is now a PIL Image ready for pytesseract
```

### pytesseract image_to_data Usage
```python
# Source: pytesseract PyPI documentation
import pytesseract
from pytesseract import Output

data = pytesseract.image_to_data(img, lang="eng+fra+deu", output_type=Output.DICT)
# data keys: level, page_num, block_num, par_num, line_num, word_num,
#            left, top, width, height, conf, text

# Filter to actual words with valid confidence
words_with_conf = [
    (data["text"][i], data["conf"][i])
    for i in range(len(data["text"]))
    if data["text"][i].strip() and data["conf"][i] > 0
]
```

### Existing QualityResult Extension Pattern
```python
# Extend existing QualityResult with signal breakdown (backward compatible)
@dataclass
class QualityResult:
    score: float
    flagged: bool
    garbled_count: int
    total_words: int
    sample_issues: list[str] = field(default_factory=list)
    sample_context: list[str] = field(default_factory=list)
    # NEW fields for composite scoring
    signal_scores: dict[str, float] = field(default_factory=dict)
    signal_details: dict[str, dict] = field(default_factory=dict)
    confidence_mean: float | None = None
```

### German Academic Vocabulary Sample
```python
GERMAN_PHILOSOPHY_TERMS = frozenset({
    # Kant
    "vernunft", "verstand", "anschauung", "urteilskraft", "pflicht",
    "kategorisch", "imperativ", "transzendental", "apriorisch",
    "erkenntnis", "erscheinung", "noumenon", "ding",
    # Hegel
    "geist", "aufhebung", "dialektik", "synthese", "entfremdung",
    "selbstbewusstsein", "absolut", "vermittlung", "wirklichkeit",
    # Husserl
    "intentionalität", "epoché", "reduktion", "lebenswelt",
    "noesis", "noema", "konstitution", "evidenz",
    # Heidegger (extending existing list)
    "lichtung", "gestell", "ereignis", "kehre", "gelassenheit",
    "grundstimmung", "unverborgenheit", "seinsgeschichte",
    # Common philosophical German
    "wissenschaft", "grundlegung", "weltanschauung", "vorstellung",
    "bestimmung", "begrifflichkeit", "zusammenhang", "beziehung",
})
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single garbled-ratio score | Composite multi-signal | This phase | More accurate quality assessment, fewer false positives |
| No OCR confidence data | pytesseract word-level confidence | This phase | Direct OCR quality measurement vs. proxy heuristics |
| English/French/Greek/Latin only | + German support | This phase | Broader academic text coverage |

**Deprecated/outdated:**
- The current `QualityAnalyzer.analyze()` method signature should remain backward-compatible but return enhanced `QualityResult` with additional fields.

## Open Questions

1. **Performance budget for confidence extraction**
   - What we know: 300 DPI render + pytesseract is ~1-3 seconds per page
   - What's unclear: Whether this is acceptable in the "existing text" path
   - Recommendation: Only use confidence signal in Tesseract/Surya paths, not "existing" path. Or make it opt-in via a `--deep-analysis` flag.

2. **Bundled word list size and source**
   - What we know: Need English + academic vocabulary; context says bundled, no external spellcheck
   - What's unclear: Optimal word list size (10K? 50K? 100K?)
   - Recommendation: Start with ~20K most common English words + academic terms. Can be generated from freely available frequency lists. Keep it small for fast set lookups.

3. **ocrmypdf hOCR intermediate access**
   - What we know: ocrmypdf uses hOCR internally (its PDF renderer is hOCR-based) but does not expose confidence
   - What's unclear: Whether the experimental API could provide access without re-running OCR
   - Recommendation: Don't rely on ocrmypdf internals. Use pytesseract separately for confidence when needed.

## Sources

### Primary (HIGH confidence)
- [pytesseract PyPI](https://pypi.org/project/pytesseract/) - `image_to_data` API, Output types, lang parameter
- [ocrmypdf Advanced docs](https://ocrmypdf.readthedocs.io/en/latest/advanced.html) - Confirmed ocrmypdf does NOT expose word confidence
- [PyMuPDF documentation](https://pymupdf.readthedocs.io/) - `get_pixmap()` for page rendering

### Secondary (MEDIUM confidence)
- [Tesseract hOCR x_wconf discussion](https://groups.google.com/g/tesseract-ocr/c/x3v9qckKJFc) - Confirmed x_wconf 0-100 range
- [hOCR parser GitHub](https://github.com/jlieth/hocr-parser) - Alternative hOCR parsing approach
- [pytesseract hOCR parsing gist](https://gist.github.com/mndrake/134b8e71f414ffbc4d34131a91aa82e0) - Example parsing code

### Tertiary (LOW confidence)
- General web search results on OCR quality scoring strategies - no single authoritative source for composite scoring approaches

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - pytesseract and PyMuPDF are well-documented, stable libraries
- Architecture: HIGH - Signal-based composite scoring is a standard pattern; codebase structure is clear
- Pitfalls: HIGH - Based on documented library behavior (pytesseract conf=-1, DPI requirements)
- German vocabulary: MEDIUM - Term lists are from domain knowledge, should be validated by user

**Research date:** 2026-01-29
**Valid until:** 2026-03-01 (stable domain, no fast-moving dependencies)
