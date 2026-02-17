# Feature Research: OCR Diagnostic Intelligence & Evaluation Tooling

**Domain:** OCR diagnostic instrumentation, LLM-based evaluation, image quality analysis
**Researched:** 2026-02-17
**Confidence:** MEDIUM-HIGH

## Scope

This document covers NEW capabilities for scholardoc-ocr's v3.0 milestone: diagnostic enrichment, struggle taxonomy, smart page selection, LLM evaluation framework, and quality scoring calibration. Existing pipeline features (two-phase OCR, composite quality scoring, cross-file batching, post-processing) are treated as foundations to build upon.

The guiding philosophy is **"measure before you fix"** -- instrument first, evaluate with ground truth second, then make targeted improvements based on data.

## Feature Landscape

### Table Stakes (Users Expect These)

Features that any serious diagnostic/evaluation system for OCR needs. Without these, the tooling provides no actionable insight beyond what already exists.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Page-level diagnostic report** | Current JSON sidecar has quality scores but not WHY a page scored low. Users need actionable diagnostics per page. | MEDIUM | Extend existing `PageResult` and JSON metadata. Add signal breakdown, struggle category, image quality metrics. |
| **CER/WER computation against ground truth** | Industry-standard OCR evaluation metrics. Cannot claim to evaluate OCR without edit-distance metrics. | LOW | Use `jiwer` library (C++-backed via RapidFuzz, fast, well-maintained). Already supports CER, WER, MER, WIL. Existing `QualityResult` provides heuristic scores; CER/WER provide absolute accuracy. |
| **Image quality metrics per page** | Blur, skew, DPI, contrast are the primary input-side factors that predict OCR failure. Must measure what enters the pipeline, not just what exits. | MEDIUM | OpenCV-based: Laplacian variance for blur, Hough/minAreaRect for skew, pixel density for effective DPI, histogram spread for contrast. PyMuPDF already renders pages to pixmaps at 300 DPI (`confidence.py` line 30). |
| **Tesseract vs Surya text diff per page** | When both engines process a page, users need to see what changed. This is the core diagnostic for the two-phase strategy. | LOW | Python `difflib` (stdlib) for structured diffs. Store Tesseract text before Surya overwrite. Currently Tesseract text is discarded when Surya replaces it. |
| **Post-processing change tracking** | The `postprocess()` chain (unicode, dehyphenate, join_paragraphs, punctuation) modifies text silently. Users need to know what changed and how much. | LOW | Compute diff before/after each transform stage. Store summary counts (chars changed, hyphens rejoined, paragraphs merged) in metadata. |
| **Ground truth storage and management** | Evaluation requires reference text. Need a structured way to store, version, and associate ground truth with specific pages of specific PDFs. | LOW | Simple directory convention: `ground_truth/{pdf_stem}/page_{N}.txt`. No database needed for 4 test PDFs. JSON manifest maps PDF hashes to ground truth versions. |
| **Evaluation result schema** | Results must be structured, versioned, and comparable across runs. Ad hoc evaluation produces ad hoc insights. | LOW | JSON schema for evaluation results: timestamp, prompt version, model, page ID, CER, WER, LLM judgments, raw scores. Enables regression tracking. |

### Differentiators (Competitive Advantage)

Features that go beyond standard OCR evaluation and make this system uniquely valuable for academic text processing.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Struggle taxonomy** | Categorize WHY pages fail, not just that they fail. Categories: scan-quality (blur/skew/noise), multilingual-confusion (Greek/Latin in English text), layout-complexity (footnotes/columns/marginalia), font-issues (unusual typefaces), content-density (mathematical notation, dense citations). Enables targeted fixes instead of blanket reprocessing. | MEDIUM | Build on existing `QualityResult.signal_scores` and `signal_details`. Add image quality signals. Use decision tree: if garbled_score low AND blur high -> "scan_quality"; if dictionary_score low AND multilingual tokens detected -> "multilingual_confusion". |
| **Smart page selection for evaluation** | Avoid evaluating entire 300-page books. Automatically select "interesting" pages: worst-scoring pages, best-scoring pages (control), gray-zone pages (near threshold), pages with signal disagreement, one random page per category. Target 10-20 pages per PDF for evaluation. | MEDIUM | Leverages existing `QualityResult` data. Selection algorithm: N worst, N best (control), N near threshold (gray zone defined as threshold +/- 0.05, already in `QualityAnalyzer.GRAY_ZONE`), N with highest signal variance, M random. |
| **LLM-as-judge evaluation via CLI** | Use `claude` CLI and `codex` CLI (through user accounts, not API) to evaluate OCR quality by sending page image + OCR text and asking for ground truth comparison. Reproducible via versioned prompt templates. | HIGH | Core complexity is prompt engineering and output parsing. Must handle: CLI invocation with image files, structured output parsing, retry on malformed responses, template versioning. User accounts mean no billing/quota management needed. |
| **Versioned prompt templates** | Prompts are the "source code" of LLM evaluation. Must be versioned, parameterized, and reproducible. Different templates for different evaluation tasks: transcription accuracy, layout fidelity, academic term preservation. | MEDIUM | YAML or Markdown templates with variable interpolation. Git-versioned alongside code. Content-addressable IDs (hash of template content) ensure reproducibility. Template categories: `transcribe`, `compare`, `judge_quality`, `identify_errors`. |
| **Signal disagreement detection** | When garbled, dictionary, and confidence signals disagree strongly, that page is diagnostically interesting. High confidence + low dictionary = engine-confident garbage. Low confidence + high dictionary = good text from bad scan. These disagreements reveal calibration issues. | LOW | Already have `signal_scores` dict in `QualityResult`. Compute pairwise disagreement: `abs(signal_a - signal_b)`. Flag pages where max disagreement exceeds threshold (e.g., 0.3). Cheap to compute, high diagnostic value. |
| **Character-level confidence mapping** | Tesseract provides per-character confidence via hOCR. Map low-confidence character clusters to identify specific problem regions within a page, not just page-level scores. | MEDIUM | Use `pytesseract.image_to_data()` with `hocr_char_boxes=1` config. Current `ConfidenceSignal` already uses word-level data. Extend to character level. Identify contiguous low-confidence regions for targeted analysis. |
| **Layout complexity scoring** | Pages with multi-column layouts, footnotes, tables, and marginalia are structurally harder for OCR. Surya's layout detection can identify these regions. Score layout complexity as a predictive signal for OCR difficulty. | HIGH | Requires Surya's `LayoutPredictor` API (separate from OCR). Count region types per page (footnotes, tables, columns). Complex layouts correlate with OCR failures. Currently not exposed by the pipeline. |
| **Evaluation dashboard (HTML report)** | Generate a single HTML file showing evaluation results: per-page scores, CER/WER trends, struggle categories, before/after diffs, LLM judgments. Viewable in any browser, no server needed. | MEDIUM | Jinja2 template with embedded CSS. Similar pattern to pytest-html. Include: summary table, per-page detail cards, score distribution charts (inline SVG or simple CSS bars). No JavaScript dependencies for maximum portability. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem valuable but create problems in this specific context.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **API-based LLM evaluation** | Seems more programmatic and scalable than CLI invocation | Requires API keys, billing management, rate limiting, token counting. Project spec explicitly uses user CLI accounts. API adds infrastructure complexity for 4 test PDFs. | Use `claude` and `codex` CLI tools. Parse structured output from stdout. Simpler, no credential management, leverages existing user subscriptions. |
| **Real-time evaluation during pipeline** | Evaluate quality as pages are processed, not after | LLM evaluation is slow (10-30s per page via CLI). Blocking the pipeline on LLM calls would make processing 10-100x slower. Diagnostic data should be collected fast, evaluated later. | Collect all diagnostic data during pipeline run. Run evaluation as a separate post-processing step. Two-stage: instrument fast, evaluate slow. |
| **Automated ground truth generation** | Let the LLM create ground truth automatically | LLM transcriptions are not ground truth -- they are another OCR hypothesis. Using LLM output as ground truth poisons the evaluation. Circular reasoning: LLM judges its own transcription quality. | Use LLM for comparative evaluation ("which is better?") not absolute ground truth. Create manual ground truth for the 4 test PDFs (small corpus, one-time effort). |
| **Full-corpus evaluation** | Evaluate every page of every PDF | Wasteful for 300-page books where 280 pages are fine. Burns LLM context and user time. Diminishing returns after evaluating representative sample. | Smart page selection: 10-20 pages per PDF covering worst, best, gray zone, and random. Extrapolate corpus quality from sample. |
| **Custom OCR model training** | Train a model on the specific corpus for better accuracy | Requires large labeled dataset (thousands of pages), GPU training infrastructure, ML expertise. Massive scope expansion for marginal gains on 4 PDFs. | Use existing engines (Tesseract, Surya) with better preprocessing. Apply post-correction with language models for specific error patterns identified by diagnostics. |
| **PDF annotation overlay** | Draw bounding boxes on the PDF showing problem regions | Modifying PDF output adds complexity. PyMuPDF can do it but the annotated PDF is a different artifact from the OCR output. Conflates diagnostic output with production output. | Generate HTML report with page images and overlaid highlights. Keep OCR output PDFs clean. Diagnostic visualization is separate from production artifacts. |
| **Continuous integration evaluation** | Run evaluation on every commit | LLM evaluation via CLI is non-deterministic and slow. CI would be flaky and expensive. 4 PDFs is not enough for statistical significance on regressions. | Run evaluation manually when making quality-affecting changes. Store results in versioned JSON for manual comparison. Use CER/WER regression tests (deterministic, fast) in CI instead. |

## Feature Dependencies

```
Image Quality Metrics (OpenCV-based)
    |
    +-- blur score, skew angle, contrast ratio, effective DPI
    |
    v
Struggle Taxonomy (categorizes WHY pages fail)
    |
    +-- requires image quality + existing signal scores
    |
    v
Smart Page Selection (picks interesting pages)
    |
    +-- requires struggle taxonomy + quality scores + signal disagreement
    |
    v
Ground Truth Storage (reference text for evaluation)
    |
    +-- simple directory convention, independent of above
    |
    v
CER/WER Computation (jiwer, against ground truth)
    |
    +-- requires ground truth storage
    |
    v
Evaluation Result Schema (structured, versioned results)
    |
    +-- requires CER/WER + ground truth mapping

Diagnostic Enrichment (independent track):
    Page-level diagnostic report
        +-- requires signal disagree + image quality + struggle taxonomy
    Tesseract vs Surya diff
        +-- requires storing pre-Surya text (pipeline change)
    Post-processing change tracking
        +-- requires instrumenting postprocess.py transforms

LLM Evaluation (depends on ground truth + diagnostics):
    Versioned Prompt Templates
        +-- independent, can build early
    LLM-as-Judge via CLI
        +-- requires prompt templates + ground truth + smart page selection
    Evaluation Dashboard (HTML report)
        +-- requires all evaluation data collected
```

### Dependency Notes

- **Image Quality Metrics are foundational:** They feed the struggle taxonomy, which feeds smart page selection. Build image quality first.
- **Ground Truth Storage is independent:** Can be created in parallel with diagnostic enrichment. Just needs directory structure and a few manually transcribed pages.
- **Tesseract vs Surya diff requires a pipeline change:** Currently, Tesseract text is overwritten by Surya text in `map_results_to_files()` (batch.py line 474). Must store Tesseract text before overwrite.
- **LLM evaluation is the final consumer:** It depends on smart page selection (to know which pages to evaluate), ground truth (for comparison), and prompt templates (for reproducibility). Build last.
- **Signal disagreement is cheap and early:** Only needs existing `QualityResult.signal_scores`. Can ship with diagnostic enrichment as a quick win.
- **Layout complexity scoring conflicts with performance goals:** Loading Surya's LayoutPredictor is expensive. Should only run during evaluation, not during production pipeline. Keep it optional/separate.

## MVP Definition

### Phase 1: Diagnostic Enrichment (Instrument the Pipeline)

Core instrumentation that collects data without changing OCR behavior.

- [ ] **Image quality metrics per page** -- blur (Laplacian variance), skew (Hough transform), contrast (histogram spread), effective DPI. Attach to `PageResult` metadata.
- [ ] **Signal disagreement detection** -- flag pages where quality signals disagree by > 0.3. Cheap, uses existing data.
- [ ] **Struggle taxonomy** -- categorize flagged pages into failure categories based on image quality + signal patterns.
- [ ] **Tesseract vs Surya text preservation** -- store Tesseract text before Surya overwrite. Enables diff computation.
- [ ] **Post-processing change tracking** -- count changes per transform stage (unicode normalizations, hyphens rejoined, paragraphs merged).
- [ ] **Enhanced page-level diagnostic report** -- extend JSON metadata with all new diagnostic fields.

### Phase 2: Evaluation Framework (Measure Against Ground Truth)

Build the evaluation infrastructure.

- [ ] **Ground truth storage** -- directory structure, manifest, initial manual transcriptions for selected pages of 4 test PDFs.
- [ ] **Smart page selection** -- algorithm to pick 10-20 representative pages per PDF for evaluation.
- [ ] **CER/WER computation** -- integrate `jiwer` for edit-distance metrics against ground truth.
- [ ] **Evaluation result schema** -- JSON schema for structured, versioned evaluation results.
- [ ] **Versioned prompt templates** -- YAML templates for LLM evaluation tasks, content-addressed.

### Phase 3: LLM Evaluation (Judge Quality with Vision Models)

Use LLMs as evaluation judges.

- [ ] **CLI invocation harness** -- invoke `claude` and `codex` CLI with page images and OCR text, parse structured output.
- [ ] **Evaluation runner** -- orchestrate evaluation across selected pages, collect results, handle errors/retries.
- [ ] **Cross-engine comparison prompts** -- templates for "which transcription is better?" comparisons.
- [ ] **Evaluation dashboard** -- HTML report with per-page results, CER/WER, LLM judgments.

### Phase 4: Targeted Improvements (Fix Based on Data)

Only after diagnostic data reveals specific problems.

- [ ] **Image preprocessing pipeline** -- apply targeted corrections (deskew, deblur, contrast enhancement) based on image quality metrics. Only for pages where diagnostics indicate input quality is the bottleneck.
- [ ] **Context-aware post-correction** -- use LLM or language model to fix specific OCR error patterns identified by diagnostics (e.g., systematic character substitutions in Greek text).
- [ ] **Quality scoring calibration** -- adjust composite score weights based on CER/WER correlation. Current weights (garbled: 0.4, dictionary: 0.3, confidence: 0.3) are heuristic; calibrate against ground truth.

### Defer Indefinitely

- [ ] **Custom model training** -- massive scope, marginal gains for 4 PDFs
- [ ] **Real-time evaluation** -- fundamentally conflicts with pipeline performance
- [ ] **Full-corpus evaluation** -- wasteful, smart page selection is sufficient
- [ ] **CI-integrated evaluation** -- non-deterministic, slow, insufficient corpus size

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Phase |
|---------|------------|---------------------|----------|-------|
| Image quality metrics | HIGH | MEDIUM | P1 | 1 |
| Signal disagreement detection | HIGH | LOW | P1 | 1 |
| Struggle taxonomy | HIGH | MEDIUM | P1 | 1 |
| Tesseract vs Surya text preservation | HIGH | LOW | P1 | 1 |
| Post-processing change tracking | MEDIUM | LOW | P1 | 1 |
| Enhanced diagnostic report | HIGH | LOW | P1 | 1 |
| Ground truth storage | HIGH | LOW | P1 | 2 |
| Smart page selection | HIGH | MEDIUM | P1 | 2 |
| CER/WER computation | HIGH | LOW | P1 | 2 |
| Evaluation result schema | MEDIUM | LOW | P1 | 2 |
| Versioned prompt templates | MEDIUM | MEDIUM | P2 | 2 |
| CLI invocation harness | HIGH | HIGH | P2 | 3 |
| Evaluation runner | HIGH | MEDIUM | P2 | 3 |
| Evaluation dashboard | MEDIUM | MEDIUM | P2 | 3 |
| Image preprocessing | MEDIUM | MEDIUM | P3 | 4 |
| Context-aware post-correction | MEDIUM | HIGH | P3 | 4 |
| Quality scoring calibration | HIGH | MEDIUM | P3 | 4 |
| Layout complexity scoring | LOW | HIGH | P3 | 4+ |

**Priority key:**
- P1: Must have -- core diagnostic and evaluation infrastructure
- P2: Should have -- enables the full evaluation workflow
- P3: Nice to have -- improvements driven by diagnostic data

## Existing Infrastructure to Build On

The current codebase provides significant foundations:

| Existing Feature | How It Feeds New Work |
|-----------------|----------------------|
| `QualityResult.signal_scores` | Direct input to signal disagreement detection |
| `QualityResult.signal_details` | Detailed breakdown for struggle taxonomy |
| `QualityAnalyzer.GRAY_ZONE = 0.05` | Smart page selection: pages near threshold |
| `PageResult.quality_score` + `PageResult.flagged` | Page selection: worst/best/gray zone |
| `ConfidenceSignal.score_from_data()` | Word-level confidence already extracted. Extend to char-level. |
| `_GarbledSignal.PATTERNS` | Pattern matching for struggle categorization |
| `PDFProcessor.extract_text_by_page()` | Page-level text extraction for ground truth comparison |
| `postprocess()` chain | Instrument each transform for change tracking |
| `processor.py` pixmap rendering | Reuse for image quality metric extraction |
| JSON metadata sidecar | Extend with diagnostic fields |
| `FlaggedPage` dataclass | Already tracks page origins across files |
| Benchmark infrastructure | Extend with evaluation benchmarks |

## Competitor Feature Analysis

| Feature | OCR-D (Historical) | OmniDocBench (CVPR 2025) | Our Approach |
|---------|--------------------|-----------------------------|--------------|
| Ground truth format | PAGE XML with glyph-level coords | JSON with bounding boxes | Plain text per page (sufficient for academic text; no layout ground truth needed) |
| Evaluation metrics | CER, WER, reading order, layout accuracy | Edit distance, TEDS, CDM | CER, WER via jiwer + LLM-as-judge for semantic accuracy |
| Page selection | Manual or exhaustive | Benchmark dataset (predefined) | Algorithmic smart selection from quality scores + struggle taxonomy |
| Failure analysis | Manual inspection | Category benchmarks | Automated struggle taxonomy with image quality correlation |
| LLM integration | None (historical focus) | LLM benchmarking (not evaluation) | LLM-as-judge for quality evaluation via CLI |
| Reproducibility | XML-based workflows | Fixed benchmark | Versioned prompt templates + evaluation result schema |
| Scope | Library-scale digitization | General document AI | Targeted: 4 academic philosophy PDFs, depth over breadth |

## Sources

### Official Documentation and Tools (HIGH confidence)
- [Tesseract Improve Quality Guide](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html) -- preprocessing recommendations, diagnostic output via tessedit_write_images
- [jiwer PyPI](https://pypi.org/project/jiwer/) -- CER, WER, MER, WIL metrics. C++ backend via RapidFuzz.
- [Python difflib](https://docs.python.org/3/library/difflib.html) -- HtmlDiff for side-by-side text comparison
- [Surya GitHub](https://github.com/datalab-to/surya) -- layout detection API, LayoutPredictor, region types (Caption, Footnote, Formula, Table, etc.)
- [OCR-D Quality Assurance Spec](https://ocr-d.de/en/spec/ocrd_eval.html) -- ground truth comparison, page-level metrics

### Research Papers and Benchmarks (MEDIUM confidence)
- [OCR Error Post-Correction with LLMs in Historical Documents](https://arxiv.org/html/2502.01205v1) -- LMs outperform LLMs for post-correction; segment-wise correction challenges
- [CLOCR-C: Context Leveraging OCR Correction](https://arxiv.org/abs/2408.17428v1) -- 60%+ CER reduction with context-aware LM correction
- [OCRBench v2](https://arxiv.org/html/2501.00321v2) -- comprehensive benchmark for multimodal OCR evaluation
- [OmniDocBench (CVPR 2025)](https://github.com/opendatalab/OmniDocBench) -- document parsing evaluation framework
- [Survey of OCR Evaluation Tools and Metrics](https://dl.acm.org/doi/10.1145/3476887.3476888) -- Flexible Character Accuracy (FCA), reading order impact on CER
- [OCR-Quality Human-Annotated Dataset](https://arxiv.org/html/2510.21774) -- 1000 PDF pages, diverse scenarios, quality assessment methods
- [LLM-as-a-Judge Guide](https://www.confident-ai.com/blog/why-llm-as-a-judge-is-the-best-llm-evaluation-method) -- methodology, reliability (85% human agreement), failure modes

### Community and Ecosystem (LOW-MEDIUM confidence)
- [LLMs for Historical OCR](https://arxiv.org/html/2501.11623v1) -- Claude Sonnet 3.5 better with whole scans, GPT-4o better with sliced images
- [Blur Detection with OpenCV](https://pyimagesearch.com/2015/09/07/blur-detection-with-opencv/) -- Laplacian variance method
- [image-quality-analysis PyPI](https://pypi.org/project/image-quality-analysis/) -- motion blur, edge density, entropy metrics
- [LLM Prompt Evaluation Guide 2025](https://www.keywordsai.co/blog/prompt_eval_guide_2025) -- evaluation-driven iteration, reproducible experiments
- [Prompt Versioning Tools 2025](https://www.braintrust.dev/articles/best-prompt-versioning-tools-2025) -- content-addressable IDs, semantic versioning

### Codebase Analysis (HIGH confidence)
- `quality.py` -- `QualityResult` with `signal_scores`, `signal_details`, `GRAY_ZONE = 0.05`
- `confidence.py` -- `ConfidenceSignal` with word-level data, extensible to char-level
- `batch.py` -- `map_results_to_files()` overwrites Tesseract text with Surya (line 474)
- `postprocess.py` -- `postprocess()` chain: normalize_unicode -> dehyphenate -> join_paragraphs -> normalize_punctuation
- `pipeline.py` -- `_tesseract_worker()` produces page-level quality analysis; Phase 2 handles Surya
- `types.py` -- `PageResult`, `FileResult`, `BatchResult` with `to_dict()` serialization

---
*Feature research for: OCR diagnostic intelligence and evaluation tooling*
*Researched: 2026-02-17*
