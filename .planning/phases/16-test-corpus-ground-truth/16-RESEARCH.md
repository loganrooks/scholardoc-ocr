# Phase 16: Test Corpus & Ground Truth - Research

**Researched:** 2026-02-17
**Domain:** Evaluation corpus design, ground truth creation, diagnostic data consumption, filesystem infrastructure
**Confidence:** HIGH

## Summary

Phase 16 builds the evaluation corpus that Phases 17-19 depend on. The core engineering work is infrastructure (directory structure, manifest, gitignore rules), running the existing pipeline with `--diagnostics --extract-text` to produce baseline data, then using diagnostic output to intelligently select pages for ground truth creation via Opus vision transcription.

Codebase analysis reveals that all the pipeline machinery already exists. The `--diagnostics` flag produces `.diagnostics.json` sidecars with per-page `struggle_categories`, `signal_scores`, `signal_disagreements`, and `has_signal_disagreement` fields. The `--extract-text` flag writes `.txt` files alongside output PDFs. The pipeline writes output to `{output_dir}/final/` with `.pdf`, `.txt`, `.json`, and `.diagnostics.json` files. PyMuPDF's `page.get_pixmap(dpi=300)` renders pages to PNG at publication quality for Opus transcription -- the exact same API already used in `diagnostics.py:analyze_image_quality()` at 150 DPI.

The main research finding is that this phase requires almost no new code. It is primarily filesystem infrastructure (dirs, gitignore, manifest JSON) plus a workflow for running existing tools. The planner should structure tasks around the revised sequencing (CORP-01 -> CORP-02 -> CORP-04 -> page selection -> CORP-03 -> manifest finalization) with clear hand-off points where human action is required (PDF symlink creation, Opus transcription, spot-checking).

**Primary recommendation:** Structure tasks as infrastructure-first, baseline-second, ground-truth-third, with helper scripts for page rendering and coverage matrix analysis to reduce manual toil.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **Page selection strategy (coverage-based, not count-based):** Selection driven by Phase 15 diagnostic data: struggle categories, gray-zone flags, signal disagreement. Two categories: difficult pages (~40-50 selected via coverage matrix) and regression pages (count determined after baseline). Total target ~60-70 pages, coverage drives the number.
- **Ground truth creation (Opus vision transcription + spot-check):** Render selected pages as images via PyMuPDF. Claude Opus transcribes from page images. Human spot-checks ~10-15% sample. If spot-check reveals systematic patterns, add targeted correction pass.
- **Ground truth fidelity (dual-layer: raw + normalized-at-comparison):** Stored ground truth is faithful transcription. Proper Unicode, paragraph structure, footnotes separated, Greek/Latin preserved, diacritics preserved. Excluded: page numbers, running headers, marginal annotations. Comparison normalization is Phase 18's responsibility.
- **Manifest design (observable metadata, not pre-labeled challenges):** Per Phase 15's lesson: don't pre-label challenge profiles. `corpus.json` with observable facts (title, author, language, page_count, scan_source), structural booleans (has_footnotes, has_greek, has_toc), diagnostic summary generated from baseline. Per-page ground truth mapping. PDF symlinks gitignored; manifest and ground truth committed.
- **Baseline as workflow input (not just reference snapshot):** Baseline = full pipeline run with `--diagnostics`. Store BOTH diagnostic sidecar AND OCR output text. Pin pipeline + engine versions in manifest. After Phase 20 improvements, re-running produces "after" baseline.
- **Revised requirement sequencing:** CORP-01 -> CORP-02 -> CORP-04 -> page selection -> CORP-03 -> manifest finalization.
- **Corpus extensibility:** Adding a document = manifest entry + PDF symlink + baseline run + ground truth files.

### Claude's Discretion
- Exact coverage matrix thresholds (how many pages per struggle category)
- Regression set size and composition (determined after seeing baseline diagnostic output)
- Ground truth file format conventions (encoding, line endings, paragraph marking)
- Manifest JSON schema structure (field names, nesting)
- Directory layout within `tests/corpus/`
- How to handle pages with complex layout (tables, equations, multi-column)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

## Standard Stack

### Core (No New Dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `PyMuPDF (fitz)` | 1.26.7 | Page rendering to PNG for Opus transcription | Already a direct dependency; `page.get_pixmap(dpi=300).save()` is the exact API |
| `json` | stdlib | Manifest read/write, diagnostic sidecar parsing | Already used throughout pipeline.py |
| `pathlib` | stdlib | Directory creation, path manipulation | Already used throughout codebase |
| `shutil` | stdlib | File copying for baseline organization | Already used in pipeline.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `unicodedata` | stdlib | NFC normalization of ground truth text | Ensuring ground truth matches postprocess.py's `normalize_unicode()` |
| `collections.Counter` | stdlib | Coverage matrix tallying | Counting pages per struggle category from diagnostic output |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyMuPDF rendering | pdf2image (poppler) | pdf2image adds poppler system dependency; PyMuPDF is already installed and proven |
| Manual Opus prompting | Automated API script | User has CLI accounts, not SDK; manual upload is simpler for ~60 pages |
| JSON manifest | YAML/TOML | JSON is already used for all structured output in the pipeline; consistency wins |

**Installation:**
```bash
# No new dependencies required -- all libraries already available
pip install -e ".[dev]"
```

## Architecture Patterns

### Recommended Directory Layout
```
tests/corpus/
├── corpus.json                           # Manifest (committed)
├── .gitignore                            # Corpus-specific ignores
├── pdfs/                                 # PDF symlinks (gitignored)
│   ├── simondon-technical-objects.pdf    # -> /user/path/to/actual/pdf
│   ├── derrida-grammatology.pdf
│   ├── derrida-margins.pdf
│   └── derrida-dissemination.pdf
├── ground_truth/                         # Ground truth text (committed)
│   ├── simondon-technical-objects/
│   │   ├── page_042.txt
│   │   ├── page_073.txt
│   │   └── ...
│   ├── derrida-grammatology/
│   │   └── ...
│   ├── derrida-margins/
│   │   └── ...
│   └── derrida-dissemination/
│       └── ...
├── baselines/                            # Baseline outputs
│   ├── simondon-technical-objects/
│   │   └── final/
│   │       ├── simondon-technical-objects.diagnostics.json  # committed
│   │       ├── simondon-technical-objects.txt               # committed
│   │       └── simondon-technical-objects.json              # committed
│   └── ... (same structure for other docs)
└── images/                               # Rendered page PNGs (gitignored)
    ├── simondon-technical-objects/
    │   ├── page_042.png
    │   └── ...
    └── ...
```

### Pattern 1: Corpus-Local Gitignore
**What:** A `.gitignore` inside `tests/corpus/` that excludes PDFs, images, and pipeline artifacts while allowing ground truth, manifest, and diagnostic JSON.
**When to use:** Always -- this is simpler than adding complex rules to the root `.gitignore`.
**Rationale:** Keeps corpus ignore rules co-located with corpus files, doesn't pollute root `.gitignore`.

```gitignore
# tests/corpus/.gitignore

# PDF files (large binaries, user-specific paths)
pdfs/

# Rendered page images (regenerable from PDFs)
images/

# Pipeline output PDFs (large binaries)
baselines/**/final/*.pdf

# Pipeline work directories and logs
baselines/**/work/
baselines/**/logs/
```

### Pattern 2: Pipeline Output as Baseline
**What:** Running the existing pipeline with `--diagnostics --extract-text` to produce baseline data.
**When to use:** CORP-04 -- after PDFs are symlinked.
**Example:**
```bash
# Run baseline for a single document
ocr --diagnostics --extract-text --force \
    -f pdfs/simondon-technical-objects.pdf \
    -o baselines/simondon-technical-objects/ \
    tests/corpus/

# Output structure:
# baselines/simondon-technical-objects/final/
#   simondon-technical-objects.diagnostics.json  # Per-page diagnostic data
#   simondon-technical-objects.txt               # OCR output text
#   simondon-technical-objects.json              # Pipeline metadata
#   simondon-technical-objects.pdf               # OCR'd PDF (gitignored)
```

### Pattern 3: Page Rendering for Opus Transcription
**What:** Using PyMuPDF to render selected pages at 300 DPI as PNG for Opus vision input.
**When to use:** After coverage matrix identifies target pages.
**Example:**
```python
# Source: Verified via PyMuPDF docs and existing diagnostics.py usage
import fitz

def render_pages(pdf_path: Path, page_numbers: list[int], output_dir: Path) -> None:
    """Render specific pages from a PDF as 300 DPI PNGs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(pdf_path)
    try:
        for page_num in page_numbers:
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300)
            pix.save(str(output_dir / f"page_{page_num:03d}.png"))
    finally:
        doc.close()
```

### Pattern 4: Coverage Matrix from Diagnostic Data
**What:** Parse `.diagnostics.json` sidecar to build a coverage matrix of struggle categories across pages.
**When to use:** After baseline run, before ground truth creation.
**Example:**
```python
import json
from collections import defaultdict

def build_coverage_matrix(diagnostics_path: Path) -> dict[str, list[int]]:
    """Map struggle categories to page numbers from diagnostic sidecar."""
    with open(diagnostics_path) as f:
        data = json.load(f)

    matrix: dict[str, list[int]] = defaultdict(list)
    for page in data["pages"]:
        diag = page.get("diagnostics", {})
        for category in diag.get("struggle_categories", []):
            matrix[category].append(page["page_number"])

        # Also capture gray_zone and signal_disagreement from flags
        if diag.get("has_signal_disagreement"):
            if "signal_disagreement" not in diag.get("struggle_categories", []):
                matrix["signal_disagreement"].append(page["page_number"])

    return dict(matrix)
```

### Anti-Patterns to Avoid
- **Pre-labeling challenge profiles:** Per CONTEXT.md decision and Phase 15's lesson, don't pre-label "challenge profiles" on documents. Observable metadata only. Phase 19 discovers actual challenges empirically from ground truth comparison.
- **Count-based page selection:** "10 pages per document" misallocates effort. Coverage-based selection (ensuring each struggle category has 2-3 examples) is more valuable for downstream analysis.
- **Absolute symlinks in committed files:** PDF symlinks themselves are gitignored, but if paths appear in the manifest, they should be relative to `tests/corpus/`.
- **Baking normalization into ground truth:** Store raw transcription. Normalization happens at comparison time (Phase 18).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Page rendering | Custom poppler wrapper | `fitz.Page.get_pixmap(dpi=300).save()` | Already a dependency, 3-line implementation |
| Diagnostic parsing | Custom sidecar reader | `json.load()` on `.diagnostics.json` | Sidecar is standard JSON, schema is self-documenting |
| Unicode normalization | Custom normalizer | `unicodedata.normalize("NFC", text)` | Matching existing `postprocess.py:normalize_unicode()` |
| Coverage analysis | Manual page review | Script parsing diagnostic JSON | 20 lines of Python vs hours of manual scanning |
| PDF text extraction | Re-running OCR | Read `.txt` from baseline output | Pipeline already extracted text during baseline |

**Key insight:** Phase 16 produces no new library code -- it consumes existing pipeline output and creates filesystem infrastructure. The "code" is helper scripts for page rendering and coverage analysis, not pipeline features.

## Common Pitfalls

### Pitfall 1: Forgetting --extract-text on baseline run
**What goes wrong:** Pipeline runs with `--diagnostics` but without `--extract-text`. The `.txt` files are written during processing but deleted at cleanup (line 802-803 of pipeline.py: `if not config.extract_text: for txt_file in final_dir.glob("*.txt"): txt_file.unlink()`).
**Why it happens:** `--diagnostics` and `--extract-text` are separate flags. Diagnostics produce the sidecar JSON, but the OCR text output requires `--extract-text` to persist.
**How to avoid:** Always use `ocr --diagnostics --extract-text --force` for baseline runs. Document this in the manifest or a README.
**Warning signs:** Baseline directory has `.diagnostics.json` and `.json` but no `.txt` file.

### Pitfall 2: 0-indexed vs 1-indexed page numbers
**What goes wrong:** Ground truth files named `page_001.txt` but PageResult uses 0-indexed `page_number`. Comparison code uses wrong page.
**Why it happens:** PDFs are conventionally described with 1-indexed pages, but the codebase uses 0-indexed throughout.
**How to avoid:** Use 0-indexed page numbers everywhere to match `PageResult.page_number`. File naming: `page_000.txt`, `page_001.txt`, etc. Manifest mapping uses integer keys matching `page_number`.
**Warning signs:** Off-by-one errors in ground truth alignment.

### Pitfall 3: Ground truth normalization leaking
**What goes wrong:** Ground truth is stored with normalization applied (e.g., ligature decomposition, paragraph joining). Phase 18 applies normalization again, double-transforming the text.
**Why it happens:** Temptation to "clean up" ground truth for readability.
**How to avoid:** Store ground truth as faithful raw transcription. Only apply NFC Unicode normalization (to ensure consistent codepoint representation). All other normalization happens at comparison time in Phase 18.
**Warning signs:** CER/WER metrics that seem systematically biased.

### Pitfall 4: Pipeline version drift
**What goes wrong:** Baseline captured with scholardoc-ocr 0.2.0, but Phase 20 improvements change pipeline behavior. Old baseline is no longer reproducible for comparison.
**Why it happens:** Versions not pinned in manifest. "Before" and "after" baselines use different pipeline versions.
**How to avoid:** Pin all versions in `corpus.json` manifest: scholardoc-ocr, tesseract, surya-ocr, marker-pdf, ocrmypdf, pymupdf. Add run date. After improvements, create a new baseline entry (don't overwrite the original).
**Warning signs:** Metric differences that don't correspond to actual changes.

### Pitfall 5: Large PDF processing time
**What goes wrong:** Baseline run on 4 philosophy PDFs (likely 200-400+ pages each) takes hours. Developer interrupts mid-run.
**Why it happens:** These are full books. Tesseract + Surya on hundreds of pages is slow.
**How to avoid:** Process one document at a time using `-f` flag. Budget 15-30 min per document for Tesseract phase. Expect Surya phase only on flagged pages (not all pages). Use `--force` to ensure Tesseract runs even if existing text layer exists.
**Warning signs:** Timeouts, partial output, system memory pressure.

### Pitfall 6: Opus transcription of degraded scans
**What goes wrong:** If scan quality is poor, Opus vision may also struggle, producing unreliable ground truth.
**Why it happens:** Opus is powerful but not omniscient -- badly degraded scans may have genuinely unreadable text.
**How to avoid:** Spot-check ~10-15% of transcriptions. For pages where Opus clearly guesses, mark them in the manifest as lower confidence. If systematic issues found (e.g., consistent ligature errors), run targeted correction pass per CONTEXT.md decision.
**Warning signs:** Opus output has [?] markers, missing characters, or obviously wrong words.

## Code Examples

### Manifest JSON Schema
```json
{
  "version": "1.0",
  "created": "2026-02-17",
  "pipeline_versions": {
    "scholardoc_ocr": "0.2.0",
    "tesseract": "5.5.2",
    "surya_ocr": "0.17.1",
    "marker_pdf": "1.10.2",
    "ocrmypdf": "16.13.0",
    "pymupdf": "1.26.7"
  },
  "documents": [
    {
      "id": "simondon-technical-objects",
      "title": "Du mode d'existence des objets techniques",
      "author": "Gilbert Simondon",
      "language": ["fr"],
      "page_count": null,
      "scan_source": "library_scan",
      "has_footnotes": true,
      "has_greek": false,
      "has_toc": true,
      "pdf_symlink": "pdfs/simondon-technical-objects.pdf",
      "baseline": {
        "path": "baselines/simondon-technical-objects/final",
        "diagnostics_file": "simondon-technical-objects.diagnostics.json",
        "text_file": "simondon-technical-objects.txt",
        "run_date": null,
        "pipeline_version": null
      },
      "diagnostic_summary": null,
      "ground_truth_pages": {}
    },
    {
      "id": "derrida-grammatology",
      "title": "Of Grammatology",
      "author": "Jacques Derrida",
      "language": ["en"],
      "page_count": null,
      "scan_source": null,
      "has_footnotes": true,
      "has_greek": true,
      "has_toc": true,
      "pdf_symlink": "pdfs/derrida-grammatology.pdf",
      "baseline": {
        "path": "baselines/derrida-grammatology/final",
        "diagnostics_file": "derrida-grammatology.diagnostics.json",
        "text_file": "derrida-grammatology.txt",
        "run_date": null,
        "pipeline_version": null
      },
      "diagnostic_summary": null,
      "ground_truth_pages": {}
    },
    {
      "id": "derrida-margins",
      "title": "Margins of Philosophy",
      "author": "Jacques Derrida",
      "language": ["en"],
      "page_count": null,
      "scan_source": null,
      "has_footnotes": true,
      "has_greek": true,
      "has_toc": true,
      "pdf_symlink": "pdfs/derrida-margins.pdf",
      "baseline": {
        "path": "baselines/derrida-margins/final",
        "diagnostics_file": "derrida-margins.diagnostics.json",
        "text_file": "derrida-margins.txt",
        "run_date": null,
        "pipeline_version": null
      },
      "diagnostic_summary": null,
      "ground_truth_pages": {}
    },
    {
      "id": "derrida-dissemination",
      "title": "Dissemination",
      "author": "Jacques Derrida",
      "language": ["en"],
      "page_count": null,
      "scan_source": null,
      "has_footnotes": true,
      "has_greek": true,
      "has_toc": true,
      "pdf_symlink": "pdfs/derrida-dissemination.pdf",
      "baseline": {
        "path": "baselines/derrida-dissemination/final",
        "diagnostics_file": "derrida-dissemination.diagnostics.json",
        "text_file": "derrida-dissemination.txt",
        "run_date": null,
        "pipeline_version": null
      },
      "diagnostic_summary": null,
      "ground_truth_pages": {}
    }
  ]
}
```

### Ground Truth File Format Convention
```text
# Example: tests/corpus/ground_truth/derrida-grammatology/page_042.txt
# UTF-8 encoded, NFC-normalized, Unix line endings (LF)
# No page numbers, headers, or marginal annotations
# Blank line between paragraphs
# Footnotes after --- separator

The history of metaphysics which, in spite of all differences, not
only from Plato to Hegel (even including Leibniz) but also, beyond
these apparent limits, from the pre-Socratics to Heidegger, always
assigned the origin of truth in general to the logos: the history of
truth, of the truth of truth, has always been -- except for a
metaphysical diversion that we shall have to explain -- the
debasement of writing and its repression outside "full" speech.

The necessary debasement of writing, its "fall" outside the full
and present speech, has always taken the form of a metaphor. It is
not a matter of inverting the literal meaning and the figurative
meaning.

---

1. Cf. my "Violence and Metaphysics," in Writing and Difference.
2. TN: The author is here playing on the French word difference.
```

### Helper Script: Render Pages for Opus Transcription
```python
#!/usr/bin/env python3
"""Render selected PDF pages as 300 DPI PNGs for Opus vision transcription.

Usage:
    python scripts/render_pages.py <document-id> <page_numbers...>

Example:
    python scripts/render_pages.py derrida-grammatology 42 73 150 201
"""
# Source: PyMuPDF official docs - page.get_pixmap(dpi=300)
import json
import sys
from pathlib import Path

import fitz


def render_pages(corpus_dir: Path, doc_id: str, page_numbers: list[int]) -> None:
    manifest_path = corpus_dir / "corpus.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    doc_entry = next(d for d in manifest["documents"] if d["id"] == doc_id)
    pdf_path = corpus_dir / doc_entry["pdf_symlink"]

    output_dir = corpus_dir / "images" / doc_id
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    try:
        for page_num in page_numbers:
            if page_num >= len(doc):
                print(f"Warning: page {page_num} out of range (max {len(doc) - 1})")
                continue
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300)
            out_path = output_dir / f"page_{page_num:03d}.png"
            pix.save(str(out_path))
            print(f"Rendered page {page_num} -> {out_path}")
    finally:
        doc.close()


if __name__ == "__main__":
    corpus_dir = Path("tests/corpus")
    doc_id = sys.argv[1]
    pages = [int(p) for p in sys.argv[2:]]
    render_pages(corpus_dir, doc_id, pages)
```

### Helper Script: Build Coverage Matrix
```python
#!/usr/bin/env python3
"""Analyze baseline diagnostics to build coverage matrix for page selection.

Usage:
    python scripts/build_coverage_matrix.py

Reads all .diagnostics.json files from tests/corpus/baselines/ and
reports which struggle categories are covered and how many pages per category.
"""
import json
from collections import defaultdict
from pathlib import Path


def analyze_baselines(corpus_dir: Path) -> None:
    manifest_path = corpus_dir / "corpus.json"
    with open(manifest_path) as f:
        manifest = json.load(f)

    all_categories: dict[str, list[tuple[str, int]]] = defaultdict(list)
    gray_zone_pages: list[tuple[str, int]] = []
    disagreement_pages: list[tuple[str, int]] = []

    for doc in manifest["documents"]:
        baseline_path = corpus_dir / doc["baseline"]["path"]
        diag_file = baseline_path / doc["baseline"]["diagnostics_file"]

        if not diag_file.exists():
            print(f"WARNING: No baseline for {doc['id']}")
            continue

        with open(diag_file) as f:
            data = json.load(f)

        for page in data["pages"]:
            diag = page.get("diagnostics", {})
            page_num = page["page_number"]
            doc_id = doc["id"]

            for cat in diag.get("struggle_categories", []):
                all_categories[cat].append((doc_id, page_num))

            if "gray_zone" in diag.get("struggle_categories", []):
                gray_zone_pages.append((doc_id, page_num))

            if diag.get("has_signal_disagreement"):
                disagreement_pages.append((doc_id, page_num))

    print("=== Coverage Matrix ===\n")
    for cat, pages in sorted(all_categories.items()):
        print(f"{cat}: {len(pages)} pages")
        for doc_id, page_num in pages[:5]:
            print(f"  {doc_id} page {page_num}")
        if len(pages) > 5:
            print(f"  ... and {len(pages) - 5} more")

    print(f"\nGray zone pages: {len(gray_zone_pages)}")
    print(f"Signal disagreement pages: {len(disagreement_pages)}")

    # Recommend minimum selection
    selected: set[tuple[str, int]] = set()
    for cat, pages in all_categories.items():
        # Take at least 2-3 per category
        for page in pages[:3]:
            selected.add(page)
    # Add all gray zone and disagreement pages
    selected.update(gray_zone_pages)
    selected.update(disagreement_pages)

    print(f"\nMinimum recommended difficult pages: {len(selected)}")
    by_doc = defaultdict(list)
    for doc_id, page_num in sorted(selected):
        by_doc[doc_id].append(page_num)
    for doc_id, pages in by_doc.items():
        print(f"  {doc_id}: {len(pages)} pages - {pages}")


if __name__ == "__main__":
    analyze_baselines(Path("tests/corpus"))
```

## Existing Codebase Integration Points

### Pipeline Output Structure (Verified)
The pipeline with `--diagnostics --extract-text --force` writes to `{output_dir}/final/`:

| File | Purpose | Committed? |
|------|---------|------------|
| `{stem}.pdf` | OCR'd PDF | No (gitignored, large binary) |
| `{stem}.txt` | Post-processed OCR text (requires `--extract-text`) | Yes |
| `{stem}.json` | Pipeline metadata (timings, engine, quality) | Yes |
| `{stem}.diagnostics.json` | Per-page diagnostic sidecar (requires `--diagnostics`) | Yes |

**Critical:** Without `--extract-text`, the `.txt` file is deleted at pipeline cleanup (line 802-803 of `pipeline.py`).

### Diagnostic Sidecar Schema (Verified from `diagnostics.py`)
```json
{
  "version": "1.0",
  "filename": "document.pdf",
  "generated_at": "2026-02-17T...",
  "pipeline_config": {"quality_threshold": 0.85, "diagnostics": true},
  "pages": [
    {
      "page_number": 0,
      "quality_score": 0.87,
      "engine": "tesseract",
      "flagged": false,
      "status": "good",
      "diagnostics": {
        "signal_scores": {"garbled": 0.92, "dictionary": 0.78, "confidence": 0.85},
        "signal_details": {"garbled": {...}, "dictionary": {...}, "confidence": {...}},
        "composite_weights": {"garbled": 0.4, "dictionary": 0.3, "confidence": 0.3},
        "signal_disagreements": [
          {"signals": ["garbled", "dictionary"], "magnitude": 0.14},
          {"signals": ["garbled", "confidence"], "magnitude": 0.07},
          {"signals": ["dictionary", "confidence"], "magnitude": 0.07}
        ],
        "has_signal_disagreement": false,
        "postprocess_counts": {"dehyphenations": 3, "paragraph_joins": 12},
        "struggle_categories": [],
        "image_quality": {"dpi": 300.0, "contrast": 0.21, "blur_score": 1547.3, "skew_angle": 0.12},
        "tesseract_text": null,
        "engine_diff": null
      }
    }
  ]
}
```

### Page Number Convention (Verified)
`PageResult.page_number` is **0-indexed** throughout the codebase (see `pipeline.py` lines 139-155: `page_number=i` where `i in range(page_count)`). Ground truth file naming and manifest page keys must use 0-indexed numbers.

### Version Information (Verified from Environment)
| Component | Version | Source |
|-----------|---------|--------|
| scholardoc-ocr | 0.2.0 | `pyproject.toml` |
| Tesseract | 5.5.2 | `tesseract --version` |
| surya-ocr | 0.17.1 | `pip show surya-ocr` |
| marker-pdf | 1.10.2 | `pip show marker-pdf` |
| ocrmypdf | 16.13.0 | `pip show ocrmypdf` |
| PyMuPDF | 1.26.7 | `fitz.version` |
| Python | 3.11.14 | `sys.version` |

## Discretion Recommendations

### Coverage Matrix Thresholds
- **Minimum 2 pages per struggle category** that appears in diagnostic output. If a category appears in only 1 document, take all instances from that document (up to 5).
- **All gray_zone pages** selected automatically (these are the most informative for threshold calibration in Phase 19).
- **All signal_disagreement pages** selected automatically (these reveal where the quality model disagrees with itself).
- If a category has 10+ pages, sample 3-4 spanning different documents for diversity.
- **Expected total:** 40-50 difficult pages, but actual count depends on baseline data. If fewer struggle categories fire than expected, the difficult set may be smaller.

### Regression Set Composition
Determined after baseline, but the selection criteria should be:
- **1 ToC/index page per document** that scores > 0.90 (tests structured page handling)
- **1 front matter page per document** (title page, copyright, etc.)
- **2-3 clean body text pages per document** scoring > 0.90 with no struggle categories
- **1 bibliography/references page per document** if present
- **Total estimate:** 15-20 pages across 4 documents
- **Purpose:** These pages should always pass quality threshold. Any regression in Phase 20 improvements that breaks these is a genuine bug.

### Ground Truth File Format
- **Encoding:** UTF-8, NFC-normalized (matching `postprocess.py:normalize_unicode()`)
- **Line endings:** Unix LF (consistent with rest of codebase)
- **Paragraph structure:** Blank line between paragraphs
- **Footnotes:** After `---` separator on its own line, numbered to match source
- **Excluded content:** Page numbers, running headers/footers, marginal annotations
- **Tables:** Plain text, columns separated by consistent spacing (not markdown table syntax, since OCR outputs plain text)
- **Equations:** Best-effort plain text transcription (not LaTeX)
- **Multi-column:** Transcribe in reading order (left column first, then right)
- **Greek/Latin:** Preserve original Unicode characters with correct diacritics

### Manifest JSON Schema
See Code Examples section above. Key design points:
- `ground_truth_pages` is a mapping from page number (string key for JSON) to relative file path
- `diagnostic_summary` is populated after baseline analysis, not pre-labeled
- `baseline.path` is relative to `tests/corpus/`
- Null values indicate "not yet populated" (phased workflow)
- Version pinning in top-level `pipeline_versions` (not per-document)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual challenge profiling | Diagnostic-data-driven page selection | Phase 15 (just completed) | Removes guessing from page selection; coverage matrix is empirical |
| Count-based page selection | Coverage-based selection | Phase 16 context discussion | Better downstream utility with fewer pages |
| Manual text transcription | Opus vision transcription | Current | Makes 60-70 pages feasible; 10-15% spot-check sufficient |
| Pre-labeled challenge categories | Observable metadata + deferred analysis | Phase 15/16 design | Prevents confirmation bias in evaluation |

## Open Questions

1. **Do the 4 named PDFs cover enough struggle categories?**
   - What we know: All 4 are philosophy texts, likely similar scan quality patterns. Derrida texts have Greek, Simondon is French-only.
   - What's unclear: Whether `bad_scan`, `language_confusion`, and `layout_error` categories will be represented. These are the weakest signal categories per Phase 15 CONTEXT.md.
   - Recommendation: Run baseline first (CORP-04). If coverage matrix shows empty categories, document the gap. The CONTEXT.md decision says adding a 5th document is "trivial" if needed. Phase 19 can only analyze what the corpus contains, and documenting what's missing is itself valuable.

2. **How accurate is Opus vision transcription on degraded scans?**
   - What we know: Opus is multimodal and handles philosophical vocabulary well. The ground truth is for OCR evaluation, not for publication.
   - What's unclear: Accuracy on low-contrast scans, blurred text, or heavily skewed pages.
   - Recommendation: Start with the easiest pages to establish a workflow. Spot-check the first 5-10 transcriptions before doing all 60-70. If systematic issues appear (e.g., consistent diacritics errors), adjust the Opus prompt or add a correction pass.

3. **Pipeline version pinning: is the current environment stable?**
   - What we know: Versions are pinned in `pyproject.toml` with minimum constraints (`>=`), not exact pins (`==`). Current versions: tesseract 5.5.2, surya-ocr 0.17.1, marker-pdf 1.10.2.
   - What's unclear: Whether a `pip install --upgrade` could change behavior between baseline and re-evaluation.
   - Recommendation: Record exact versions in manifest at baseline time. Consider adding a `pip freeze` snapshot alongside the manifest if reproducibility becomes critical. For now, the manifest version recording is sufficient.

## Sources

### Primary (HIGH confidence)
- **Codebase analysis:** `pipeline.py` (output structure, flag behavior), `diagnostics.py` (sidecar schema, struggle categories), `types.py` (PageResult schema, 0-indexed page_number), `postprocess.py` (normalization functions), `cli.py` (--diagnostics and --extract-text flags)
- **PyMuPDF /pymupdf/pymupdf Context7:** Page rendering API (`get_pixmap(dpi=300).save()`), verified against existing `diagnostics.py` usage
- **Environment verification:** Exact package versions confirmed via `pip show` and `tesseract --version` in the development venv

### Secondary (MEDIUM confidence)
- **Phase 15 CONTEXT.md and RESEARCH.md:** Diagnostic data model design, struggle category definitions, two-tier gating architecture
- **Phase 16 CONTEXT.md:** User decisions on sequencing, page selection, ground truth fidelity, manifest design

### Tertiary (LOW confidence)
- **Opus vision transcription accuracy:** No empirical data on Opus transcription quality for degraded philosophy scans. Confidence is based on general knowledge of Claude's multimodal capabilities. Spot-check will validate.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all tools already in use
- Architecture: HIGH -- directory layout and manifest design are straightforward; pipeline output structure verified from source
- Pitfalls: HIGH -- all pitfalls verified from actual pipeline code (especially the `--extract-text` cleanup behavior)
- Ground truth workflow: MEDIUM -- Opus transcription accuracy is unverified for this specific domain

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (stable domain; no external dependencies to track)
