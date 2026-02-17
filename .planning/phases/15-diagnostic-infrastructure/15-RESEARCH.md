# Phase 15: Diagnostic Infrastructure - Research

**Researched:** 2026-02-17
**Domain:** Pipeline instrumentation, image analysis, structured diffing, dataclass serialization
**Confidence:** HIGH

## Summary

Phase 15 instruments the existing OCR pipeline to capture diagnostic data that explains *why* each page scored the way it did. The core insight from codebase analysis is that **most of the data already exists** -- `QualityAnalyzer.analyze()` already computes per-signal `SignalResult` objects with scores and details, but the pipeline discards them after computing the composite score. The primary engineering work is (1) threading this existing data through to `PageResult`, (2) adding new cheap computations (signal disagreement, struggle categories, postprocess counters), and (3) implementing the `--diagnostics`-gated expensive features (image quality via OpenCV, Tesseract text preservation, JSON sidecar output).

Key findings: OpenCV (`opencv-python-headless 4.11.0`) is already a transitive dependency via `surya-ocr`, so DIAG-01 image quality metrics need no new dependencies. Dataclass pickling through `ProcessPoolExecutor` works perfectly with an `Optional[PageDiagnostics]` field -- measured at 0.7KB per page for always-on diagnostics. The existing `QualityResult` already contains `signal_scores`, `signal_details`, and `confidence_mean` -- these just need to be preserved rather than discarded.

**Primary recommendation:** Structure this as a bottom-up build: diagnostic dataclasses first, then wire always-captured data through the pipeline, then add `--diagnostics`-gated features, then JSON sidecar output.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Two-tier diagnostic gating**: Always-captured (DIAG-02, DIAG-03, DIAG-05, DIAG-06, DIAG-07) vs `--diagnostics`-gated (DIAG-01, DIAG-04, DIAG-08)
- **Struggle categories as array**: Each page gets array of all applicable categories, not single dominant label. 8 categories: `bad_scan`, `character_confusion`, `vocabulary_miss`, `layout_error`, `language_confusion`, `signal_disagreement`, `gray_zone`, `surya_insufficient`
- **Signal disagreement**: Store pairwise magnitudes + boolean flag at 0.3 default threshold
- **Diff granularity**: Word-level stored, both raw texts preserved. Structure: additions, deletions, substitutions with summary counts
- **Sidecar placement**: `{stem}.diagnostics.json` alongside output PDF, one per PDF

### Claude's Discretion
- Image quality metric thresholds and implementation details (OpenCV vs PyMuPDF for specific measurements)
- Exact boolean detection rules for each struggle category (initial heuristics, Phase 19 will calibrate)
- Diagnostic data class/dataclass structure
- JSON sidecar schema structure (field names, nesting)
- How to pipe always-captured diagnostic data through the existing multiprocessing pipeline
- Post-processing counter implementation

### Deferred Ideas (OUT OF SCOPE)
- Layout complexity scoring via LayoutPredictor (EVAL-F02)
- Language confidence signal for `language_confusion` detection
- Diagnostic dashboard/visualization (EVAL-F01)
</user_constraints>

## Standard Stack

### Core (No New Dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `dataclasses` | stdlib | Diagnostic data structures | Already used throughout codebase (PageResult, FileResult, etc.) |
| `difflib` | stdlib | Word-level Tesseract-vs-Surya diff | SequenceMatcher.get_opcodes() provides exact additions/deletions/substitutions |
| `opencv-python-headless` | 4.11.0 | Image quality metrics (blur, skew) | Already installed as transitive dep via surya-ocr |
| `Pillow` | 10.4.0 | Image rendering bridge (PyMuPDF pixmap to OpenCV) | Already installed as dep of pytesseract |
| `PyMuPDF (fitz)` | >=1.24.0 | Page rendering to pixmap, DPI extraction | Already a direct dependency, used in confidence.py and processor.py |
| `numpy` | 2.4.2 | Array ops for OpenCV image analysis | Already installed as transitive dep |
| `json` | stdlib | JSON sidecar output | Already used in pipeline.py for metadata output |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pickle` | stdlib | Serialization through ProcessPoolExecutor | Automatic -- dataclasses pickle natively |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| OpenCV Laplacian | Pillow FIND_EDGES filter | Pillow works but OpenCV Laplacian is more precise and already available |
| OpenCV HoughLinesP | Pillow row projection | Pillow has no skew detection; OpenCV is the standard approach |
| Custom diff | `difflib.unified_diff` | unified_diff is line-oriented; SequenceMatcher on word lists gives structured ops |

**Installation:**
```bash
# No new dependencies required -- all libraries already available
pip install -e ".[dev]"
```

## Architecture Patterns

### Recommended Project Structure
```
src/scholardoc_ocr/
    diagnostics.py       # NEW: PageDiagnostics dataclass, struggle categorizer, signal disagreement detector, image quality analyzer, text differ
    types.py             # MODIFIED: Add Optional[PageDiagnostics] to PageResult
    quality.py           # MODIFIED: Return QualityResult (already has signal data -- no change needed in analyze())
    postprocess.py       # MODIFIED: Add counter tracking to each transform, return PostprocessStats
    pipeline.py          # MODIFIED: Wire diagnostics through _tesseract_worker and run_pipeline
    cli.py               # MODIFIED: Add --diagnostics flag to PipelineConfig
```

### Pattern 1: Diagnostic Data Attachment via Optional Field
**What:** Add `diagnostics: PageDiagnostics | None = None` to the existing `PageResult` dataclass.
**When to use:** This is the core pattern -- diagnostic data rides alongside page results through the entire pipeline.
**Why this works:** Python dataclasses with Optional fields pickle perfectly (verified: 223 bytes per page). The field defaults to None, so all existing code constructing PageResult continues to work without changes. The `to_dict()` method gains a conditional diagnostic section.

```python
# Source: Verified via codebase analysis of types.py
@dataclass
class PageResult:
    page_number: int
    status: PageStatus
    quality_score: float
    engine: OCREngine
    flagged: bool = False
    text: str | None = None
    diagnostics: PageDiagnostics | None = None  # NEW

    def to_dict(self, include_text: bool = False) -> dict:
        d: dict = {
            "page_number": self.page_number,
            "status": str(self.status),
            "quality_score": self.quality_score,
            "engine": str(self.engine),
            "flagged": self.flagged,
        }
        if include_text and self.text is not None:
            d["text"] = self.text
        if self.diagnostics is not None:
            d["diagnostics"] = self.diagnostics.to_dict()
        return d
```

### Pattern 2: Always-Captured Diagnostics in Tesseract Worker
**What:** The `_tesseract_worker` function already calls `analyzer.analyze_pages()` which returns `QualityResult` objects containing `signal_scores`, `signal_details`, and `confidence_mean`. Currently these are used only to compute `page_qualities` and `bad_pages`, then discarded. Wire them into `PageDiagnostics`.
**When to use:** Phase 1 (Tesseract) processing -- the worker already has all the data.

```python
# In _tesseract_worker, after analyzer.analyze_pages():
tess_page_results = analyzer.analyze_pages(tess_page_texts)

for i in range(page_count):
    qr = tess_page_results[i] if i < len(tess_page_results) else None
    diag = build_always_diagnostics(qr, threshold=threshold) if qr else None
    pages.append(PageResult(
        page_number=i,
        status=...,
        quality_score=...,
        engine=OCREngine.TESSERACT,
        flagged=...,
        text=...,
        diagnostics=diag,
    ))
```

### Pattern 3: Postprocess Counters via Return Value
**What:** Each postprocess function (dehyphenate, join_paragraphs, etc.) currently returns only the transformed text. Add an optional counter parameter or return a tuple.
**When to use:** DIAG-05 postprocess change tracking.
**Recommendation:** Use a mutable counter dict passed through the chain, avoiding signature changes that break existing callers.

```python
def dehyphenate(text: str, terms=None, counts: dict | None = None) -> str:
    """Rejoin line-break hyphens. If counts dict provided, increment 'dehyphenations'."""
    # ... existing logic ...
    if counts is not None:
        counts["dehyphenations"] = dehyphenation_count
    return result
```

### Pattern 4: Diagnostics-Gated Expensive Operations
**What:** Image quality analysis and text preservation only run when `PipelineConfig.diagnostics = True`.
**When to use:** DIAG-01 (image quality), DIAG-04 (text preservation + diff).

```python
# In _tesseract_worker, gated by config_dict["diagnostics"]:
if config_dict.get("diagnostics", False):
    image_metrics = analyze_image_quality(input_path, page_num)
    diag.image_quality = image_metrics
```

### Anti-Patterns to Avoid
- **Storing diagnostic data in a separate parallel structure:** Don't maintain a `dict[int, PageDiagnostics]` alongside `list[PageResult]`. The diagnostics belong ON the PageResult to prevent index mismatch bugs.
- **Re-running quality analysis to get signal data:** The quality analyzer already computes everything. Don't call it twice -- capture the result on the first pass.
- **Using complex nested dataclasses that don't pickle:** All diagnostic data must be primitive types, lists, dicts, or simple dataclasses. No callables, generators, or file handles.
- **Modifying QualityResult to hold diagnostics:** Keep QualityResult as-is (it's a quality-domain object). Create a separate PageDiagnostics that consumes QualityResult data.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Word-level text diff | Custom word comparator | `difflib.SequenceMatcher(None, words_a, words_b).get_opcodes()` | Handles insertions, deletions, substitutions with correct alignment. `get_opcodes()` returns tagged operations directly |
| Blur detection | Custom pixel variance calculator | `cv2.Laplacian(gray, cv2.CV_64F).var()` | Industry-standard Laplacian variance method; lower variance = more blur |
| Skew angle detection | Custom line angle estimation | `cv2.HoughLinesP()` on Canny edges, then median angle | Probabilistic Hough robust to noise; median angle handles outlier lines |
| PDF page rendering | Custom rasterizer | `fitz.Page.get_pixmap(dpi=150)` then convert to numpy array | PyMuPDF renders at configurable DPI; 150 DPI sufficient for analysis (not OCR) |
| DPI detection | Manual image info parsing | `fitz.Page.get_image_info()` returns list with xres/yres per embedded image | PyMuPDF extracts embedded image metadata directly |
| JSON serialization of dataclasses | Custom recursive serializer | `dataclasses.asdict()` or custom `to_dict()` method pattern | Already used throughout codebase (PageResult.to_dict, FileResult.to_dict) |

**Key insight:** Every "expensive" component of DIAG-01 (image quality metrics) already has a well-tested library implementation available without new dependencies. The only custom code needed is the glue: rendering a page, running the analysis, and structuring the result.

## Common Pitfalls

### Pitfall 1: Breaking Existing Pipeline Consumers
**What goes wrong:** Adding a required field to PageResult breaks all existing code that constructs PageResult without it.
**Why it happens:** PageResult is constructed in multiple places: `_tesseract_worker`, `map_results_to_files`, test fixtures, MCP server.
**How to avoid:** Use `diagnostics: PageDiagnostics | None = None` with default None. All existing constructors continue to work unchanged. Add diagnostics only where data is available.
**Warning signs:** Test failures in test_pipeline.py, test_batch.py, test_types.py, test_mcp_server.py.

### Pitfall 2: Serialization Failures in ProcessPoolExecutor
**What goes wrong:** Complex objects in PageDiagnostics fail to pickle when returned from `_tesseract_worker`.
**Why it happens:** ProcessPoolExecutor uses pickle to transfer results between processes. Objects with file handles, generators, or unpicklable types fail silently or raise cryptic errors.
**How to avoid:** Use ONLY primitive types in PageDiagnostics: `float`, `int`, `str`, `bool`, `list`, `dict`, `None`. Verified: a realistic PageDiagnostics pickles at 762 bytes per page. No numpy arrays or PIL Images in the dataclass.
**Warning signs:** `pickle.PicklingError` or `AttributeError: Can't pickle` at runtime.

### Pitfall 3: Image Quality Analysis at Wrong DPI
**What goes wrong:** Rendering pages at 300 DPI for quality analysis when 150 DPI suffices wastes 4x memory and 2x time.
**Why it happens:** The confidence.py module renders at 300 DPI for OCR accuracy, so developers copy that pattern.
**How to avoid:** DIAG-01 image analysis doesn't need OCR-quality rendering. Use 150 DPI for blur/contrast/skew analysis. This cuts pixmap memory from ~25MB to ~6MB per page at typical academic paper dimensions.
**Warning signs:** Memory spikes during `--diagnostics` runs, especially on large PDFs.

### Pitfall 4: Postprocess Counter Breaks Existing Callers
**What goes wrong:** Changing `postprocess()` return type from `str` to `tuple[str, dict]` breaks every caller.
**Why it happens:** `postprocess()` is called in `_tesseract_worker` (line 100, 166) and `run_pipeline` (line 531).
**How to avoid:** Pass an optional mutable dict parameter for counters. Default to None. Callers that don't pass it get identical behavior. Only the diagnostic-aware call sites pass a counter dict.
**Warning signs:** TypeError at call sites: "cannot unpack non-tuple str".

### Pitfall 5: Struggle Category Rules That Are Too Aggressive
**What goes wrong:** Struggle categories fire on nearly every page, making them meaningless.
**Why it happens:** Thresholds set too loosely. For example, `gray_zone` triggers when score is within 0.05 of threshold -- but many pages naturally land there.
**How to avoid:** Phase 15 is measurement apparatus, not diagnosis. Set conservative initial thresholds that err toward under-reporting. Phase 19 will calibrate. Empty arrays are fine -- better than false positives.
**Warning signs:** >50% of pages getting 3+ struggle categories in normal runs.

### Pitfall 6: Tesseract Text Not Preserved Before Surya Overwrites It
**What goes wrong:** In `map_results_to_files()`, Surya text replaces `page_result.text` in-place. If we capture Tesseract text AFTER this, we've already lost it.
**Why it happens:** The Surya phase mutates PageResult objects directly (batch.py line 475-479).
**How to avoid:** Capture Tesseract text into `diagnostics.tesseract_text` BEFORE calling `map_results_to_files()`. The preservation must happen in `run_pipeline()` before the Surya mapping loop.
**Warning signs:** `diagnostics.tesseract_text` equals `page_result.text` for Surya-processed pages (they should differ).

## Code Examples

### Diagnostic Dataclass Structure
```python
# Source: Designed based on CONTEXT.md decisions and codebase analysis
from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class SignalDisagreement:
    """A pair of signals that disagree beyond threshold."""
    signals: list[str]   # e.g. ["garbled", "confidence"]
    magnitude: float     # absolute difference

@dataclass
class EngineDiff:
    """Structured word-level diff between Tesseract and Surya output."""
    additions: list[str]              # words Surya added
    deletions: list[str]              # words Surya removed
    substitutions: list[dict[str, str]]  # [{"old": "teh", "new": "the"}, ...]
    summary: dict[str, int]           # {"additions": N, "deletions": N, "substitutions": N}

@dataclass
class PageDiagnostics:
    """Per-page diagnostic data. Always-captured fields are non-optional."""

    # DIAG-02: Signal breakdown (always captured)
    signal_scores: dict[str, float] = field(default_factory=dict)
    signal_details: dict[str, dict] = field(default_factory=dict)
    composite_weights: dict[str, float] = field(default_factory=dict)

    # DIAG-03: Signal disagreement (always captured)
    signal_disagreements: list[SignalDisagreement] = field(default_factory=list)
    has_signal_disagreement: bool = False

    # DIAG-05: Postprocess counts (always captured)
    postprocess_counts: dict[str, int] = field(default_factory=dict)

    # DIAG-06: Struggle categories (always captured)
    struggle_categories: list[str] = field(default_factory=list)

    # DIAG-01: Image quality (--diagnostics only)
    image_quality: dict[str, float | None] | None = None

    # DIAG-04: Engine comparison (--diagnostics only)
    tesseract_text: str | None = None
    engine_diff: EngineDiff | None = None

    def to_dict(self) -> dict:
        d = {
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
            d["engine_diff"] = {
                "additions": self.engine_diff.additions,
                "deletions": self.engine_diff.deletions,
                "substitutions": self.engine_diff.substitutions,
                "summary": self.engine_diff.summary,
            }
        return d
```

### Building Diagnostics from QualityResult
```python
# Source: Codebase analysis of quality.py QualityResult fields
from scholardoc_ocr.quality import QualityResult

DISAGREEMENT_THRESHOLD = 0.3

def build_always_diagnostics(
    qr: QualityResult,
    threshold: float,
) -> PageDiagnostics:
    """Build always-captured diagnostics from an existing QualityResult."""
    # DIAG-02: Signal breakdown -- already computed
    signal_scores = qr.signal_scores  # {"garbled": 0.92, "dictionary": 0.85, ...}
    signal_details = qr.signal_details

    # Determine which weight set was used
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
        struggle_categories=categories,
    )
```

### Signal Disagreement Detection (DIAG-03)
```python
# Source: CONTEXT.md decision -- store magnitudes, flag at 0.3
from itertools import combinations

def compute_signal_disagreements(
    signal_scores: dict[str, float],
) -> list[SignalDisagreement]:
    """Compute pairwise signal disagreement magnitudes."""
    disagreements = []
    for (name_a, score_a), (name_b, score_b) in combinations(signal_scores.items(), 2):
        magnitude = abs(score_a - score_b)
        disagreements.append(SignalDisagreement(
            signals=[name_a, name_b],
            magnitude=round(magnitude, 4),
        ))
    return disagreements
```

### Image Quality Analysis (DIAG-01)
```python
# Source: Verified OpenCV 4.11.0 and PyMuPDF already available
import cv2
import numpy as np
import fitz

def analyze_image_quality(pdf_path, page_num: int) -> dict[str, float | None]:
    """Compute image quality metrics for a PDF page. Requires --diagnostics."""
    with fitz.open(pdf_path) as doc:
        page = doc[page_num]

        # DPI from embedded images
        images = page.get_image_info()
        if images:
            avg_dpi = sum(img.get("xres", 0) for img in images) / len(images)
        else:
            avg_dpi = None

        # Render at 150 DPI for analysis (not 300 -- saves 4x memory)
        pix = page.get_pixmap(dpi=150)
        img_array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)

        # Convert to grayscale
        if pix.n >= 3:
            gray = cv2.cvtColor(img_array[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            gray = img_array[:, :, 0]

        # Blur via Laplacian variance (lower = blurrier)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        blur_score = float(laplacian.var())

        # Contrast via pixel standard deviation / 255
        contrast = float(np.std(gray)) / 255.0

        # Skew via Hough transform
        skew_angle = _detect_skew(gray)

    return {
        "dpi": avg_dpi,
        "contrast": round(contrast, 4),
        "blur_score": round(blur_score, 2),
        "skew_angle": round(skew_angle, 2) if skew_angle is not None else None,
    }

def _detect_skew(gray: np.ndarray) -> float | None:
    """Detect page skew angle using Hough line transform."""
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)
    if lines is None or len(lines) == 0:
        return None
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        # Filter to near-horizontal lines (text lines)
        if abs(angle) < 45:
            angles.append(angle)
    return float(np.median(angles)) if angles else None
```

### Word-Level Diff (DIAG-04)
```python
# Source: stdlib difflib, verified behavior
import difflib

def compute_engine_diff(tesseract_text: str, surya_text: str) -> EngineDiff:
    """Compute structured word-level diff between engine outputs."""
    words_a = tesseract_text.split()
    words_b = surya_text.split()

    sm = difflib.SequenceMatcher(None, words_a, words_b)

    additions = []
    deletions = []
    substitutions = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            additions.extend(words_b[j1:j2])
        elif tag == "delete":
            deletions.extend(words_a[i1:i2])
        elif tag == "replace":
            substitutions.append({
                "old": " ".join(words_a[i1:i2]),
                "new": " ".join(words_b[j1:j2]),
            })

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
```

### Struggle Category Classification (DIAG-06)
```python
# Source: CONTEXT.md decisions on categories and signal availability
# These are initial heuristics -- Phase 19 will calibrate

def classify_struggle(
    signal_scores: dict[str, float],
    composite_score: float,
    threshold: float,
    image_quality: dict | None = None,
    engine: str | None = None,
    surya_score: float | None = None,
) -> list[str]:
    """Assign all applicable struggle categories to a page."""
    categories = []

    garbled = signal_scores.get("garbled", 1.0)
    dictionary = signal_scores.get("dictionary", 1.0)
    confidence = signal_scores.get("confidence")

    # bad_scan: image quality metrics indicate poor input
    # Strong signal when image_quality available (--diagnostics)
    # Fallback: very low confidence + very low garbled suggests unreadable input
    if image_quality:
        if (image_quality.get("blur_score", 999) < 50
            or image_quality.get("contrast", 1.0) < 0.1):
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
        if any(p > 0.3 for p in pairs):
            categories.append("signal_disagreement")
    elif abs(garbled - dictionary) > 0.3:
        categories.append("signal_disagreement")

    # gray_zone: score near threshold boundary
    if abs(composite_score - threshold) < 0.05:
        categories.append("gray_zone")

    # surya_insufficient: page went through Surya but still flagged
    if engine == "surya" and surya_score is not None and surya_score < threshold:
        categories.append("surya_insufficient")

    return categories
```

### JSON Sidecar Schema (DIAG-08)
```json
{
    "version": "1.0",
    "filename": "document.pdf",
    "generated_at": "2026-02-17T14:30:00Z",
    "pipeline_config": {
        "quality_threshold": 0.85,
        "diagnostics": true
    },
    "pages": [
        {
            "page_number": 0,
            "quality_score": 0.82,
            "engine": "tesseract",
            "flagged": true,
            "diagnostics": {
                "signal_scores": {
                    "garbled": 0.91,
                    "dictionary": 0.78,
                    "confidence": 0.65
                },
                "signal_details": {
                    "garbled": {"garbled_count": 5, "total_words": 180},
                    "dictionary": {"known_count": 140, "unknown_structured": 20, "unknown_garbled": 10, "total": 170},
                    "confidence": {"word_count": 180, "mean_conf": 65.2, "min_conf": 12}
                },
                "composite_weights": {"garbled": 0.4, "dictionary": 0.3, "confidence": 0.3},
                "signal_disagreements": [
                    {"signals": ["garbled", "confidence"], "magnitude": 0.26},
                    {"signals": ["garbled", "dictionary"], "magnitude": 0.13},
                    {"signals": ["dictionary", "confidence"], "magnitude": 0.13}
                ],
                "has_signal_disagreement": false,
                "postprocess_counts": {
                    "dehyphenations": 3,
                    "paragraph_joins": 12,
                    "unicode_normalizations": 1,
                    "punctuation_fixes": 4
                },
                "struggle_categories": ["gray_zone"],
                "image_quality": {
                    "dpi": 300.0,
                    "contrast": 0.72,
                    "blur_score": 245.8,
                    "skew_angle": 0.3
                },
                "tesseract_text": "The original Tesseract output...",
                "engine_diff": {
                    "additions": ["the", "a"],
                    "deletions": ["teh"],
                    "substitutions": [
                        {"old": "phcnomenology", "new": "phenomenology"}
                    ],
                    "summary": {"additions": 2, "deletions": 1, "substitutions": 1}
                }
            }
        }
    ]
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Quality score as single float | Multi-signal composite (garbled + dictionary + confidence) | v2.0 Phase 2 | Signals already exist -- just not exposed |
| Discard signal details after scoring | Preserve signal details in QualityResult | v2.0 Phase 2 | QualityResult already has signal_scores and signal_details fields |
| Postprocess as black box | Postprocess with change tracking | Phase 15 (new) | Enables understanding what post-processing changed |
| No image quality assessment | OpenCV-based page image analysis | Phase 15 (new) | Requires rendering pages (costly) -- hence gating |

**Key realization:** The codebase is *already halfway there*. `QualityResult` has `signal_scores: dict[str, float]` and `signal_details: dict[str, dict]` populated by `QualityAnalyzer.analyze()`. The pipeline calls `analyzer.analyze_pages()` and gets back full QualityResult objects. It just extracts `.score` and `.flagged` and throws the rest away. Phase 15's biggest contribution for always-captured data is simply *not throwing away* what's already computed.

## Open Questions

### 1. DPI Detection for Non-Image PDFs
- **What we know:** `page.get_image_info()` returns embedded image resolution. For scanned PDFs (image-based), this gives the scan DPI.
- **What's unclear:** For born-digital PDFs (text-based), there are no embedded images. DPI is meaningless in that context.
- **Recommendation:** Return `None` for DPI when no embedded images exist. The `image_quality` dict uses `float | None` for each metric. Phase 19 analysis will determine whether DPI is a useful signal.

### 2. Postprocess Counter Accuracy for Surya Text
- **What we know:** Surya returns Markdown text that also goes through `postprocess()`. But Surya output differs structurally from Tesseract output.
- **What's unclear:** Whether dehyphenation counts for Surya text are meaningful (Surya may not introduce line-break hyphens).
- **Recommendation:** Track counters regardless. Phase 19 can analyze whether Surya postprocess counts differ systematically from Tesseract counts. If counters are always zero for Surya, that's useful information too.

### 3. Struggle Category Threshold Tuning
- **What we know:** Initial heuristic thresholds are educated guesses.
- **What's unclear:** What percentage of pages will trigger each category with these defaults.
- **Recommendation:** Ship with conservative thresholds. Log category distributions in test runs. Phase 19 will calibrate using ground truth data.

## Sources

### Primary (HIGH confidence)
- **PyMuPDF** -- Codebase imports: `fitz` (pymupdf>=1.24.0). Pixmap DPI, image info, page rendering verified in project's own confidence.py and processor.py
- **OpenCV** -- `opencv-python-headless 4.11.0` installed via surya-ocr dependency. Laplacian, Canny, HoughLinesP verified working in project venv
- **Pillow** -- `PIL 10.4.0` installed via pytesseract dependency. ImageFilter.FIND_EDGES, ImageStat verified available
- **difflib** -- Python stdlib. SequenceMatcher.get_opcodes() verified to produce exact additions/deletions/substitutions
- **pickle** -- Python stdlib. Dataclass with Optional[PageDiagnostics] pickles at 223 bytes (empty) to 762 bytes (typical always-on) to 4580 bytes (full diagnostics)
- **Codebase analysis** -- types.py, quality.py, pipeline.py, postprocess.py, batch.py, cli.py all read and analyzed for integration points

### Secondary (MEDIUM confidence)
- [PyMuPDF Pixmap docs](https://pymupdf.readthedocs.io/en/latest/pixmap.html) -- DPI settings, resolution properties
- [Python difflib docs](https://docs.python.org/3/library/difflib.html) -- SequenceMatcher API
- [Pillow ImageStat docs](https://pillow.readthedocs.io/en/stable/reference/ImageStat.html) -- Statistical image analysis
- [Pillow ImageFilter docs](https://pillow.readthedocs.io/en/stable/reference/ImageFilter.html) -- FIND_EDGES as Laplacian

### Tertiary (LOW confidence)
- Struggle category thresholds are initial heuristics based on reasoning about signal behavior, not empirical data. Phase 19 will calibrate.

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** -- All libraries already installed, verified in project venv, no new dependencies
- Architecture: **HIGH** -- Codebase thoroughly analyzed, integration points identified, pickling verified
- Pitfalls: **HIGH** -- Based on direct code reading of pipeline.py, batch.py, types.py
- Struggle categories: **LOW** -- Threshold heuristics are educated guesses pending Phase 19 calibration
- Image quality metrics: **MEDIUM** -- OpenCV methods are well-established, but thresholds for "bad scan" vs "good scan" are domain-specific and untested

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (stable domain -- no fast-moving dependencies)
