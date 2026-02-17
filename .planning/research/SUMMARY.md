# Project Research Summary

**Project:** scholardoc-ocr v3.0 Diagnostic Intelligence
**Domain:** OCR quality evaluation and diagnostic instrumentation
**Researched:** 2026-02-17
**Confidence:** HIGH

## Executive Summary

The v3.0 milestone adds diagnostic instrumentation and LLM-based evaluation to an existing hybrid OCR pipeline (Tesseract + Surya). The research reveals that the project's existing dependency tree is remarkably well-suited for this work: Pillow, numpy, scipy, opencv-python-headless, and pydantic are already installed as transitive dependencies via marker-pdf and surya-ocr. No new production dependencies are required. The only new system requirement is CLI tools (`claude` and `codex` via npm) for LLM-based evaluation.

The recommended approach follows a "measure before you fix" philosophy: instrument the pipeline to capture diagnostic data (image quality metrics, signal breakdowns, timing), build an evaluation framework using LLM-as-judge via CLI subprocess, analyze the evaluation results to identify systematic quality issues, then make targeted improvements based on data. This approach avoids premature optimization and ensures changes are grounded in evidence from a test corpus.

The key risk is coupling evaluation to pipeline execution, which would make OCR runs 10-100x slower due to expensive LLM calls. The mitigation is strict separation: diagnostic data collection runs during OCR (lightweight, no new overhead), while LLM evaluation runs as a separate post-hoc workflow on output artifacts. Smart page selection (10-20 pages per PDF instead of full corpus) further reduces evaluation cost by 80-90%.

## Key Findings

### Recommended Stack

The v3.0 milestone requires **zero new production dependencies**. Every library needed for diagnostic features is either already a direct dependency (PyMuPDF, Rich), already a transitive dependency (Pillow, numpy, scipy, opencv-python-headless, pydantic, rapidfuzz), or part of Python's standard library (subprocess, difflib, json, statistics).

**Core technologies:**
- **Pillow + numpy** (already transitive): Image quality metrics via ImageStat (contrast, histogram stats), PyMuPDF pixmap rendering (DPI extraction) — already used in confidence.py
- **opencv-python-headless** (already transitive via surya): Skew detection (Hough transform), noise estimation (Laplacian variance) — avoids adding scikit-image
- **scipy.stats** (already transitive via scikit-learn): Pearson/Spearman correlation for quality score calibration against ground truth
- **pydantic** (already transitive via marker-pdf): Evaluation result schemas with JSON Schema generation for LLM structured output validation
- **subprocess** (stdlib): CLI invocation of `claude` and `codex` for LLM-as-judge evaluation — user requirement is account-based CLI, not API SDK
- **difflib** (stdlib): Structured diffs between Tesseract and Surya output, unified diff generation for reports

**System requirements (not pip-installable):**
```bash
npm install -g @anthropic-ai/claude-code  # For LLM evaluation
npm install -g @openai/codex              # For LLM evaluation
```

**Key insight:** Avoid adding redundant packages (scikit-image for skew, jsonschema for validation, fuzzywuzzy for fuzzy matching) that duplicate what transitive deps already provide.

### Expected Features

**Must have (table stakes):**
- Page-level diagnostic report — extend existing PageResult JSON with signal breakdown, image quality metrics, struggle category
- CER/WER computation against ground truth — industry-standard OCR evaluation metrics via jiwer library
- Image quality metrics per page — blur (Laplacian variance), skew (Hough), contrast (histogram), DPI (PyMuPDF)
- Tesseract vs Surya text diff — preserve Tesseract text before Surya overwrite, compute structured diff
- Post-processing change tracking — count changes per transform stage (dehyphenation, paragraph joining)
- Ground truth storage and management — directory convention for reference text, manifest for corpus metadata
- Evaluation result schema — structured, versioned JSON for evaluation results enabling regression tracking

**Should have (competitive):**
- Struggle taxonomy — categorize page failures by root cause (scan quality, multilingual confusion, layout complexity, font issues)
- Smart page selection — algorithmic selection of 10-20 pages per PDF (worst, best, gray zone, signal disagreement) instead of exhaustive evaluation
- LLM-as-judge evaluation via CLI — use `claude`/`codex` CLI as subprocess for quality evaluation with page image + OCR text
- Versioned prompt templates — templates as files with git history, content-addressable IDs for reproducibility
- Signal disagreement detection — flag pages where garbled/dictionary/confidence signals disagree by >0.3 (reveals calibration issues)
- Character-level confidence mapping — extend existing word-level confidence to character clusters for targeted diagnosis
- Evaluation dashboard — single HTML file with per-page results, CER/WER trends, struggle categories, before/after diffs

**Defer (v2+):**
- Layout complexity scoring — requires separate LayoutPredictor load (expensive), only valuable during evaluation not production
- Custom OCR model training — massive scope, requires thousands of labeled pages, ML infrastructure
- Real-time evaluation during pipeline — fundamentally conflicts with performance goals (LLM calls are 1-2s each)
- Full-corpus evaluation — wasteful, smart page selection provides 80-90% insight with 10-20% cost
- CI-integrated evaluation — LLM evaluation is non-deterministic and slow, insufficient corpus for statistical significance

### Architecture Approach

The architecture maintains strict separation between four activities: (a) diagnostic data capture runs during OCR (tight coupling to pipeline), (b) evaluation runs post-hoc on artifacts (loose coupling, separate workflow), (c) analysis consumes evaluation results (no coupling to pipeline), and (d) targeted improvements modify quality/postprocess modules based on analysis findings.

**Major components:**
1. **diagnostics.py** — PageDiagnostics dataclass attached to PageResult.diagnostics (optional dict field), DiagnosticCollector called from _tesseract_worker and run_pipeline to capture image metrics, signal breakdowns, timing
2. **eval/ subpackage** — runner.py (subprocess claude/codex invocation), templates/ (versioned prompts + JSON schemas), corpus.py (test corpus management with manifest), results.py (result storage and comparison), cli_adapter.py (abstraction over CLI differences)
3. **analysis.py** — score distribution analysis, threshold sensitivity, signal correlation, false positive/negative detection, produces human-readable recommendations for quality.py adjustments
4. **Modified types.py** — add optional `diagnostics: dict | None = None` field to PageResult, backward-compatible enrichment
5. **Modified pipeline.py** — call DiagnosticCollector at key points when --diagnostics flag enabled
6. **Modified cli.py** — add --diagnostics flag and evaluate subcommand

**Key pattern:** Optional diagnostic enrichment — add metadata to PageResult without breaking existing consumers. DiagnosticCollector instantiated per worker (not singleton) since _tesseract_worker runs in subprocess pool.

**Corpus management:** tests/corpus/ with gitignored PDF symlinks, committed corpus.json manifest describing expected files, committed ground_truth/ text files for reference pages.

### Critical Pitfalls

**From v4 (Diagnostic Intelligence specific):**

1. **Coupling LLM evaluation to pipeline execution** — Running LLM evaluation inside run_pipeline makes processing 10-100x slower (1-2s per page). Prevention: Strict separation — pipeline captures diagnostic data, evaluation runs as separate post-hoc workflow. Smart page selection reduces evaluated pages by 80-90%.

2. **Unversioned prompt templates** — Embedding prompts as string literals makes iteration impossible, evaluation results non-reproducible. Prevention: Store templates as files in eval/templates/, load at runtime, git tracks history. Pair each prompt template with JSON schema for structured output validation.

3. **DiagnosticCollector as singleton** — _tesseract_worker runs in subprocess pool, singletons don't survive process boundaries. Prevention: Create DiagnosticCollector per worker invocation, attach collected data to PageResult before returning from worker.

4. **Automated quality threshold adjustments** — Having analysis.py automatically update quality.py weights removes human judgment. Prevention: Output recommendations as report, human reviews and applies changes. Quality tuning requires domain expertise.

5. **Storing large PDFs in git** — Committing test corpus PDFs bloats repository. Prevention: Commit only manifest (corpus.json) and ground truth text files. PDFs referenced via symlinks in tests/corpus/pdfs/, gitignored.

**From v2 (still relevant to new diagnostic code):**

6. **Logging from ProcessPoolExecutor workers silently lost** — With spawn start method (macOS default), worker logs vanish. Prevention: QueueHandler in workers sending to Manager().Queue() with QueueListener in main process. Test on macOS specifically.

7. **Unicode normalization inconsistency** — Tesseract outputs NFD, Surya outputs NFC. Prevention: Apply unicodedata.normalize('NFC', text) as first post-processing step before any other transforms. Critical for diagnostic text diff accuracy.

**From v1 (foundational, apply to new modules):**

8. **PyMuPDF file handle leaks on exceptions** — C-level descriptors leak without proper cleanup. Prevention: Use context managers (with fitz.open(path) as doc:) for all PyMuPDF operations in diagnostics.py image quality extraction.

9. **Fragile index-based page mapping** — Positional indices break if any page is skipped. Prevention: Use explicit page identifiers (file + page_number), assert length matches before mapping in diagnostic result aggregation.

## Implications for Roadmap

Based on research, suggested phase structure for v3.0:

### Phase 15: Diagnostic Infrastructure Foundation
**Rationale:** Must instrument pipeline before evaluation can run. Lightweight changes to existing types and pipeline orchestration. No new dependencies, minimal risk.
**Delivers:** Enriched PageResult with diagnostics field, image quality metrics (DPI, contrast, blur, skew), signal breakdown capture, --diagnostics CLI flag
**Addresses:** Table stakes features — page-level diagnostic report, image quality metrics
**Avoids:** Pitfall #8 (file handle leaks) by using context managers for PyMuPDF, Pitfall #3 (DiagnosticCollector singleton) by instantiating per worker
**Research needs:** None — extends existing processor.py and confidence.py patterns

### Phase 16: Ground Truth and Corpus Management
**Rationale:** Evaluation framework needs test data. Independent of diagnostic capture, can build in parallel. Creates foundation for all subsequent evaluation work.
**Delivers:** tests/corpus/ structure, corpus.json manifest, ground truth text for 4 test PDFs (10-20 pages each), corpus.py management module
**Addresses:** Table stakes — ground truth storage and management
**Avoids:** Pitfall #5 (storing PDFs in git) via symlink pattern
**Research needs:** None — simple directory structure and manifest schema

### Phase 17: Evaluation Framework (LLM-as-Judge)
**Rationale:** Requires both diagnostic data (Phase 15) and corpus (Phase 16) to be useful. Core capability for quality validation. Template-driven design enables iteration without code changes.
**Delivers:** eval/ subpackage with runner.py (CLI subprocess), templates/ (versioned prompts + schemas), cli_adapter.py (claude/codex abstraction), smart page selection algorithm, evaluate CLI subcommand
**Addresses:** Differentiator features — LLM-as-judge via CLI, versioned prompt templates, smart page selection
**Avoids:** Pitfall #1 (coupling to pipeline) via separate workflow, Pitfall #2 (unversioned templates) via file-based templates with git history
**Research needs:** Prompt engineering iteration — likely need `/gsd:research-phase` to develop effective evaluation prompts after seeing initial results

### Phase 18: CER/WER Metrics and Result Storage
**Rationale:** Provides quantitative evaluation alongside qualitative LLM judgments. Requires ground truth (Phase 16) and evaluation runner (Phase 17). Enables baseline tracking.
**Delivers:** jiwer integration for CER/WER/MER/WIL metrics, results.py (result storage + comparison), evaluation result schema (JSON), eval_results/ directory structure with baselines
**Addresses:** Table stakes — CER/WER computation, evaluation result schema
**Avoids:** N/A — straightforward integration, well-documented jiwer library
**Research needs:** None — jiwer is well-documented, standard usage

### Phase 19: Analysis and Calibration Tooling
**Rationale:** Consumes evaluation results from Phases 17-18. Identifies systematic quality issues and produces actionable recommendations. Gateway to Phase 20 improvements.
**Delivers:** analysis.py with score distribution analysis, threshold sensitivity, signal correlation (scipy.stats), false positive/negative detection, human-readable reports
**Addresses:** Differentiator feature — signal disagreement detection (during analysis)
**Avoids:** Pitfall #4 (automated adjustments) by outputting recommendations only, human applies changes
**Research needs:** None — standard statistical analysis with scipy

### Phase 20: Targeted Quality Improvements
**Rationale:** Data-driven changes based on Phase 19 analysis findings. Should only happen after evaluation reveals specific issues. Avoids premature optimization.
**Delivers:** Quality threshold/weight adjustments in quality.py, dictionary.py whitelist expansions, postprocess.py transform improvements, re-run evaluation to measure impact
**Addresses:** Closes loop — improvements driven by diagnostic data
**Avoids:** All v2 post-processing pitfalls (#12 dehyphenation, #13 Unicode normalization, #16 footnote corruption) by applying lessons learned
**Research needs:** Possible — if analysis reveals domain-specific issues (e.g., Greek OCR patterns), may need targeted research

### Phase 21 (Optional): Evaluation Dashboard
**Rationale:** Nice-to-have visualization after evaluation framework proves valuable. HTML generation is straightforward.
**Delivers:** Single HTML file with per-page results, CER/WER trends, struggle categories, before/after diffs (Jinja2 template, no JS dependencies)
**Addresses:** Differentiator feature — evaluation dashboard
**Avoids:** N/A — simple templating, no new complexity
**Research needs:** None — pytest-html provides reference pattern

### Phase Ordering Rationale

- **Phases 15-16 are parallelizable foundations:** Diagnostic capture and corpus setup are independent, both required for Phase 17
- **Phase 17 is the critical path:** Evaluation framework depends on both foundations, enables all subsequent phases
- **Phases 18-19 build on evaluation output:** CER/WER metrics and analysis consume evaluation results, natural sequence
- **Phase 20 is the payoff:** Data-driven improvements only make sense after evaluation reveals what to improve
- **Phase 21 is polish:** Dashboard is valuable but not blocking for core functionality

**Dependency flow:** (15 + 16) → 17 → 18 → 19 → 20 → [21]

### Research Flags

**Phases likely needing deeper research during planning:**
- **Phase 17 (Evaluation Framework):** Prompt engineering is iterative — initial templates will need refinement after seeing real evaluation results. Plan for `/gsd:research-phase` after MVP evaluation runs to optimize prompts based on response quality.
- **Phase 20 (Targeted Improvements):** If Phase 19 analysis reveals domain-specific patterns (e.g., systematic OCR errors in Greek text, specific academic term misrecognitions), may need targeted research on academic OCR post-correction techniques.

**Phases with standard patterns (skip research-phase):**
- **Phase 15 (Diagnostic Infrastructure):** Extends existing processor.py and confidence.py patterns, image quality metrics via opencv/Pillow are well-documented
- **Phase 16 (Ground Truth Management):** Simple directory structure and JSON manifest, no novel techniques
- **Phase 18 (CER/WER Metrics):** jiwer library is well-documented with clear examples, straightforward integration
- **Phase 19 (Analysis Tooling):** scipy.stats for correlation is standard statistical analysis
- **Phase 21 (Dashboard):** Jinja2 templating follows pytest-html pattern

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All required libraries already installed as transitive deps, verified via pip list. CLI tools (claude, codex) are user requirements. No dependency discovery risk. |
| Features | MEDIUM-HIGH | Table stakes features grounded in OCR evaluation literature (CER/WER, image quality metrics). Differentiator features (LLM-as-judge, struggle taxonomy) based on recent research papers but less battle-tested in production. |
| Architecture | HIGH | Clean separation of concerns (diagnostic capture vs evaluation vs analysis) grounded in existing pipeline patterns. Subprocess-based CLI invocation is proven approach. Optional PageResult enrichment maintains backward compatibility. |
| Pitfalls | HIGH | v1-v2 pitfalls grounded in actual codebase bugs. v4 pitfalls (evaluation-specific) based on documented FastMCP issues and multiprocessing patterns from existing code. Prevention strategies tested. |

**Overall confidence:** HIGH

### Gaps to Address

- **Prompt template effectiveness:** Initial evaluation prompt templates are educated guesses. Will need iteration after seeing real LLM responses. Plan for refinement cycle in Phase 17 planning.

- **Struggle taxonomy decision tree:** The categorization logic (scan-quality vs multilingual-confusion vs layout-complexity) needs validation against real corpus data. Phase 15 implementation should capture raw diagnostic data first, taxonomy classification can be refined in Phase 19 analysis.

- **Smart page selection algorithm parameters:** Suggested selection (N worst, N best, N gray zone, M random) has placeholder numbers. Actual N/M values should be determined empirically — start conservative (5 of each category = 20 pages/PDF), adjust based on evaluation cost vs insight gained.

- **Ground truth transcription effort:** Manual transcription of 10-20 pages per PDF × 4 PDFs = 40-80 pages. Research assumes this is feasible one-time effort. If corpus grows, may need semi-automated transcription workflow. Address during Phase 16 execution if manual effort becomes bottleneck.

## Sources

### Primary (HIGH confidence)
- **Existing codebase analysis** — types.py, pipeline.py, quality.py, confidence.py, processor.py, batch.py (verified current implementation patterns, integration surfaces, quality signal structure)
- **Pillow ImageStat Documentation** (v12.1.1) — histogram-based image statistics, contrast/brightness extraction via stddev
- **PyMuPDF Pixmap Documentation** — DPI control, image extraction with DPI metadata via extract_image(xref)
- **Claude Code CLI Reference** — --print, --output-format json, --json-schema, --model, --max-turns flags for structured evaluation
- **Codex CLI Reference** — exec, --json, --output-schema, --model, --ephemeral for non-interactive evaluation
- **Python difflib Documentation** — SequenceMatcher, unified_diff, HtmlDiff for text comparison
- **SciPy pearsonr/spearmanr** (v1.17.0) — correlation computation for quality score calibration
- **Pydantic Documentation** (v2.12.5) — JSON Schema generation via model_json_schema(), validation

### Secondary (MEDIUM confidence)
- **jiwer PyPI** — CER, WER, MER, WIL metrics with C++ backend via RapidFuzz (well-maintained, 1M+ downloads/month)
- **OCR-D Quality Assurance Spec** — ground truth comparison patterns, page-level evaluation metrics
- **Tesseract Improve Quality Guide** — image quality preprocessing recommendations, diagnostic output patterns
- **OpenCV Hough Transform tutorial** (Felix Abecassis) — skew detection implementation pattern with cv2.HoughLinesP
- **Pdfquad: PDF Quality Assessment** (Johan van der Knijff) — PyMuPDF + Pillow for batch quality metrics, compression analysis
- **OCR Accuracy Metrics Survey** (ACM 2022) — Flexible Character Accuracy (FCA), reading order impact on CER
- **LLM-as-a-Judge Guide** (Confident AI) — methodology, reliability (85% human agreement), failure modes
- **OCR Error Post-Correction with LLMs** (arXiv 2502.01205v1) — LMs outperform LLMs for post-correction, segment-wise challenges
- **CLOCR-C: Context Leveraging OCR Correction** (arXiv 2408.17428v1) — 60%+ CER reduction with context-aware correction

### Tertiary (LOW confidence, needs validation)
- **OmniAI OCR Benchmark** — LLM-as-judge pattern for OCR with GPT-4o (methodology not fully documented)
- **LLMs for Historical OCR** (arXiv 2501.11623v1) — Claude Sonnet 3.5 vs GPT-4o performance comparison (small sample size)
- **image-quality-analysis PyPI** — motion blur, edge density, entropy metrics (library unmaintained since 2019, avoid)

---
*Research completed: 2026-02-17*
*Ready for roadmap: yes*
