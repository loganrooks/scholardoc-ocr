# Project Research Summary

**Project:** scholardoc-ocr
**Domain:** Academic text OCR pipeline (hybrid Tesseract + Surya)
**Researched:** 2026-01-28
**Confidence:** HIGH

## Executive Summary

scholardoc-ocr is a hybrid OCR pipeline for academic texts that uses a two-phase strategy: fast Tesseract OCR first, then expensive Surya/Marker deep learning OCR only on pages below a quality threshold. The codebase suffers from critical architectural problems that prevent it from functioning correctly: Surya results are processed but never written back to output files, cross-file page mapping is fragile and prone to silent corruption, and the pipeline conflates library logic with CLI presentation making programmatic use impossible.

The research reveals a clear path forward. The current technology stack (ocrmypdf, marker-pdf, PyMuPDF, Rich) is correct for this domain with no better alternatives available. The problems are architectural: no library API boundary, UI coupled into core logic, fragile index-based cross-file page mapping, and resource management issues (file handle leaks, CPU oversubscription, ML model lifecycle). The rearchitecture must prioritize establishing a clean library/CLI separation, fixing the critical Surya write-back bug, and moving to per-file batching to eliminate cross-file index mapping.

Key risks center on three areas: (1) ML model lifecycle management (Surya models are 2GB and must load once per pipeline run, not per file), (2) PyMuPDF file handle leaks that hit OS descriptor limits on batch processing, and (3) the existing quality analysis being too simplistic (regex-only) when OCR engines already provide confidence scores. The recommended approach is a bottom-up rebuild starting with foundation modules (PDF utils, quality analysis), then OCR backends (Tesseract, Surya wrappers), then engine orchestration, and finally CLI presentation layer.

## Key Findings

### Recommended Stack

The current OCR stack is optimal and should be retained. Research found no better alternatives worth migration cost. The stack consists of four core libraries, each best-in-class for its purpose: ocrmypdf (Tesseract wrapper with preprocessing and PDF/A output), marker-pdf (Surya deep learning OCR for complex layouts), PyMuPDF/fitz (fastest Python PDF manipulation), and Rich (terminal UI). The only addition needed is click for CLI argument parsing to replace argparse, providing better subcommand support and type validation for the library/CLI separation.

**Core technologies:**
- **ocrmypdf (>=16.0.0)**: Tesseract wrapper with PDF/A output — Best-in-class integration, handles preprocessing (deskew, denoise), no real Python alternative
- **marker-pdf (>=1.0.0)**: Surya deep learning OCR — Only maintained Python package wrapping Surya models, SOTA accuracy for academic text with multilingual support
- **PyMuPDF/fitz (>=1.24.0)**: PDF page manipulation — Fastest for extract/insert pages and text extraction, no serious competitor for this use case
- **Rich (>=13.0.0)**: Terminal UI — Standard Python CLI presentation, must be isolated behind callback interface for library mode
- **click (>=8.1.0)**: CLI framework (ADD) — Replace argparse for better subcommand support and clean library/CLI separation

**Critical pattern:** Library-first architecture with progress callbacks. Core pipeline must not import Rich or any UI code. CLI provides Rich-based callbacks; library users provide their own or get silent operation. Surya models must lazy-load once per pipeline run and share across files via main process (PyTorch GPU models cannot serialize across ProcessPoolExecutor workers).

### Expected Features

The pipeline already implements most table-stakes features but is missing critical programmatic access. Users expect multi-language support (currently has English/French/Greek/Latin, needs German for Continental philosophy), page-level quality scoring, batch processing with progress, and idempotent re-runs. The major gap is the lack of library/programmatic API — the tool is CLI-only today, blocking integration with other tools and requiring manual file handling.

**Must have (table stakes):**
- Searchable PDF + plain text output — Already implemented
- Multi-language support for academic texts — Have eng/fra/ell/lat, need deu (German)
- Page-level quality scoring — Have regex-based, needs enhancement
- Library/programmatic API — MISSING, blocks integration use cases
- Structured result reporting — MISSING, results printed not returned cleanly

**Should have (differentiators):**
- Hybrid OCR engine fallback — Already core design, best quality-to-cost ratio
- OCR engine confidence scores — High-value addition, Tesseract already computes word-level confidence via hOCR
- Dictionary-based validation — Catches real-word substitutions regex misses (hunspell/enchant integration)
- Multi-signal quality analysis — Beyond garbled text to layout errors and systematic misrecognitions
- Academic term awareness — Have whitelist, extend to configurable domain dictionaries

**Defer (v2+):**
- N-gram perplexity scoring — Adds model dependencies, moderate value over dictionary checks
- Comparative scoring (run both engines) — Expensive, better as opt-in "max quality" mode
- Export formats (Markdown, EPUB) — Useful but not core to OCR quality problem
- Layout consistency checks — Complex, benefits fewer documents than other improvements

**Quality signals priority:** (1) OCR engine confidence scores from Tesseract hOCR output, (2) dictionary lookup for real-word substitutions, (3) extended character-level statistics, (4) layout consistency checks. Current regex-only approach is the weakest signal available.

### Architecture Approach

The recommended architecture separates concerns into five focused modules: CLI (argument parsing and Rich rendering), engine (orchestration and parallel dispatch), Tesseract wrapper, Surya wrapper, and PDF utilities. The key insight is that Tesseract (CPU-bound, subprocess-based) can run in parallel via ProcessPoolExecutor, while Surya (GPU-bound, PyTorch models) must run sequentially in the main process but benefits from per-file batching. This eliminates the current fragile cross-file page index mapping that causes silent data corruption.

**Current critical problems:**
1. Pipeline conflates orchestration, worker logic, and UI rendering in one 600-line file
2. No library API — run_pipeline() couples config to CLI concerns and prints Rich output as side effect
3. Fragile cross-file Surya batching — pages from all files combined, processed, mapped back by positional index (breaks on any page skip/failure)
4. PyMuPDF file handle leaks — fitz.open() without context managers, hits OS descriptor limits
5. CPU oversubscription — nested parallelism (ProcessPoolExecutor + ocrmypdf --jobs) without resource coordination

**Major components:**
1. **cli.py** — Thin wrapper: argparse -> config -> engine -> Rich rendering. No logic, only presentation
2. **engine.py** — Pure orchestration: parallel Tesseract dispatch, sequential Surya with model sharing, result aggregation. Returns typed results, accepts optional progress callback
3. **tesseract.py** — ocrmypdf subprocess wrapper, isolated from pipeline concerns
4. **surya.py** — Marker/Surya model loading and per-file batch inference. Lazy-load models once, reuse across files
5. **pdf.py** — PyMuPDF operations with context managers: extract text/pages, combine pages

**Data flow:** Input PDFs -> engine.process_directory() -> Phase 1 (parallel Tesseract via ProcessPoolExecutor, quality analysis flags bad pages) -> Phase 2 (main process loads Surya models once, processes each file's bad pages independently, no cross-file mapping) -> list[FileResult] with page-level results -> CLI formats for display

**Critical constraint:** Surya runs in main process because PyTorch GPU models cannot be pickled or shared across processes. Phase 1 is embarrassingly parallel (Tesseract). Phase 2 is sequential across files but GPU-parallel within files. This must be explicit in architecture to prevent future attempts to parallelize Surya across processes.

### Critical Pitfalls

The codebase contains four critical bugs that must be fixed before any feature work. These are not theoretical risks — they are actual broken behaviors discovered through code analysis.

1. **Surya output discarded after processing** — Phase 2 runs Surya OCR (30-60s model load, GPU processing), maps results back to files, logs "pages enhanced", then never writes the improved text to output files. The loop at pipeline.py:564-567 iterates but has no write step. Users see success messages but get Tesseract-quality text. Prevention: integration test that verifies output file content contains Surya text after Phase 2.

2. **PyMuPDF file handle leaks** — Every fitz.open() in PDFProcessor methods only calls doc.close() on happy path. Exceptions leak file handles. combine_pages_from_multiple_pdfs opens one doc per page in a loop — one exception leaks all handles. Processing 50+ files hits OS limits (macOS default ulimit: 256). Prevention: context managers everywhere (with fitz.open() as doc:), low-ulimit stress test.

3. **Fragile index-based page mapping** — Phase 2 maps Surya results to files via positional index into all_bad_pages list. If any page fails to extract or Surya returns fewer results, indices shift and every subsequent page maps to wrong file/position. Silent data corruption across documents. Prevention: per-file Surya batching eliminates cross-file mapping entirely, use explicit page IDs not positional indices.

4. **CPU oversubscription in nested parallelism** — ProcessPoolExecutor spawns N processes, each running ocrmypdf with --jobs=max_workers/num_files threads. With 1 large PDF and 8 workers: 1 process x 8 ocrmypdf threads plus Ghostscript/unpaper subprocesses. Causes thrashing and OOM on large files. Prevention: set ocrmypdf --jobs=1 per worker, let ProcessPoolExecutor handle parallelism, single resource budget.

**Moderate pitfalls:** ML model lifecycle (must load once per run, not per file), CLI-to-library extraction breaking error handling (library code must never sys.exit or import Rich), testing without deterministic fixtures (mock OCR engines, use synthetic PDFs), temp file cleanup failures filling disk (use TemporaryDirectory), Marker API instability across versions (pin strictly, wrap imports in adapter module).

## Implications for Roadmap

The rearchitecture must follow a strict bottom-up dependency order to enable incremental testing. Each phase builds on previous work and can be validated independently before proceeding. The critical insight is that fixing the architectural problems enables all feature improvements — attempting feature work on the broken architecture will fail.

### Phase 1: Foundation and Data Structures

**Rationale:** Define clean boundaries before any refactoring. This phase has no dependencies and establishes the contract all other phases implement. Must come first to prevent CLI concerns from leaking into library code during extraction.

**Delivers:**
- Clean data types (OCRConfig, FileResult, PageResult, QualityResult)
- Exception hierarchy (OCRError, QualityError, ModelLoadError)
- ProgressCallback protocol for UI decoupling
- pdf.py module with context-managed PyMuPDF operations

**Addresses:** Library API (table stakes), structured result reporting (table stakes), file handle leaks (critical pitfall #2)

**Avoids:** CLI-to-library extraction breaking error handling (moderate pitfall #6), UI coupling into library code

### Phase 2: Quality Analysis Enhancement

**Rationale:** Quality scoring is independent of OCR engines and can be built/tested in isolation. Current regex-only approach is the weakest available signal. Enhancing this before engine refactoring means better flagging of bad pages when Surya integration is fixed.

**Delivers:**
- Tesseract hOCR confidence score extraction
- Dictionary-based validation (pyenchant/hunspell)
- Extended character-level statistics
- Composite quality score (weighted: 35% engine confidence, 30% dictionary, 20% garbled regex, 15% layout)
- German language support

**Addresses:** Engine confidence scores (differentiator, highest-value quality signal), dictionary validation (differentiator), German support (table stakes for philosophy texts)

**Avoids:** Quality threshold as single global number (minor pitfall #11)

**Testing:** Synthetic PDFs with known text, pre-captured OCR output for scoring tests, no live OCR dependency

### Phase 3: OCR Backend Modules

**Rationale:** Extract Tesseract and Surya wrappers from monolithic processor.py into focused modules. These depend only on pdf.py and can be tested independently. Fixes the Surya model lifecycle and lazy-loading patterns.

**Delivers:**
- tesseract.py: ocrmypdf subprocess wrapper with clean error handling
- surya.py: Marker model lazy-loading, per-file batch processing
- Model manager pattern: load once, reuse across files
- Lazy import pattern (don't load torch/marker at module level)

**Addresses:** Surya model lifecycle (moderate pitfall #5), Marker API instability (moderate pitfall #9)

**Avoids:** ML models loading multiple times, ProcessPoolExecutor serialization issues with GPU models

**Uses:** PyMuPDF context managers from Phase 1, quality analysis from Phase 2

### Phase 4: Engine Orchestration

**Rationale:** Core pipeline logic with fixed architecture. Per-file Surya batching eliminates fragile cross-file index mapping. Tesseract runs parallel via ProcessPoolExecutor, Surya runs sequential in main process with model sharing. This is where the critical Surya write-back bug gets fixed.

**Delivers:**
- engine.py: process_file(), process_directory() library API
- Phase 1: Parallel Tesseract (ProcessPoolExecutor), quality analysis flags bad pages
- Phase 2: Sequential per-file Surya (main process, shared models)
- Resource-aware parallelism (single CPU budget, ocrmypdf --jobs=1)
- Temp file management with TemporaryDirectory
- Integration test: verify Surya text appears in final output

**Addresses:** Surya output discarded (critical pitfall #1), fragile page mapping (critical pitfall #3), CPU oversubscription (critical pitfall #4)

**Avoids:** Cross-file page index mapping, nested parallelism conflicts

**Uses:** All backend modules from Phase 3, quality analysis from Phase 2

**Testing:** Multi-file batches with known bad pages, verify page-level text assignment, low-ulimit stress tests

### Phase 5: CLI Presentation Layer

**Rationale:** Last because it depends on engine API. Thin wrapper that only handles argument parsing and Rich rendering. All logic lives in engine.py. CLI can be completely rewritten without touching library code.

**Delivers:**
- click-based CLI replacing argparse
- Rich progress callback implementation
- Error message formatting (translate exceptions to user messages)
- Result table/panel rendering

**Addresses:** Library/CLI separation pattern from stack research, click adoption

**Avoids:** UI in library code (anti-pattern #1), sys.exit in library code

**Uses:** engine.py API exclusively, no direct access to backend modules

### Phase Ordering Rationale

The bottom-up order is non-negotiable due to hard dependencies:

- **Phase 1 must come first:** Data structures and contracts prevent CLI concerns leaking during extraction. pdf.py fixes file handle leaks before they're propagated to new modules.

- **Phase 2 is independent:** Quality analysis has no engine dependencies, can be built in parallel with or before Phase 3, but results improve Phase 4 testing by providing better page flagging.

- **Phase 3 before Phase 4:** Engine orchestration calls backend modules. Building backends first enables focused testing (mock single files, verify subprocess/model behavior) before complex orchestration.

- **Phase 4 before Phase 5:** CLI wraps engine API. Building engine first enables library use cases immediately and ensures CLI is genuinely thin (if logic appears in CLI, it's a bug).

This grouping avoids pitfalls: Quality before engine means better test fixtures. Backends before orchestration isolates model lifecycle bugs. Engine before CLI prevents architecture backsliding.

### Research Flags

**Phases with standard patterns (skip research-phase):**
- **Phase 1:** Foundation work — Python dataclasses, exception hierarchies, PyMuPDF API are well-documented
- **Phase 5:** CLI presentation — click and Rich are extensively documented with clear patterns

**Phases likely needing deeper research during planning:**
- **Phase 2 — Quality analysis:** Dictionary validation and hOCR parsing may need library API research. Hunspell/pyenchant usage patterns for multilingual text need verification. Composite scoring weights may need tuning based on sample PDFs.
- **Phase 3 — Surya backend:** Marker API has changed across versions. Need to verify current import paths, model loading API, and per-page text extraction. Pin exact version and document API surface.
- **Phase 4 — Engine orchestration:** Resource budgeting for ProcessPoolExecutor + ocrmypdf parallelism needs experimentation. Optimal worker count formula and memory limits need validation on target hardware.

**No research needed:** Tesseract/ocrmypdf integration (well-established), PyMuPDF operations (clear docs), ProcessPoolExecutor patterns (standard library).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Current stack is optimal, alternatives evaluated and rejected with clear rationale. Versions flagged for manual verification (training data cutoff ~May 2025) but choices are sound. |
| Features | MEDIUM-HIGH | Table stakes and differentiators identified from domain knowledge. Quality signals prioritization is solid but weights for composite scoring need tuning. No web verification available. |
| Architecture | HIGH | Grounded in direct codebase analysis of actual bugs. Problems are concrete not theoretical. Recommended patterns are established Python best practices. Component boundaries tested in similar projects. |
| Pitfalls | HIGH | All critical pitfalls derived from line-by-line code analysis of current implementation. These are real bugs not hypothetical risks. Prevention strategies are specific and testable. |

**Overall confidence:** HIGH

The research is grounded in actual codebase analysis (not theoretical) and established Python patterns. The main uncertainty is around library version numbers (training data cutoff) and optimal resource budgeting parameters (needs experimentation). The architectural problems are concrete and the solutions are well-understood patterns.

### Gaps to Address

Research limitations due to Context7 and WebSearch being unavailable:

- **Library versions:** ocrmypdf, marker-pdf, PyMuPDF versions are from training data (cutoff ~May 2025). Need manual verification from PyPI before pinning in pyproject.toml. Run `pip index versions <package>` to get current versions.

- **Marker API current state:** Marker/Surya import paths and API may have changed. Current code uses `from marker.converters.pdf import PdfConverter` and `from marker.models import create_model_dict`. Verify these imports work with current marker-pdf version in development environment before Phase 3.

- **Tesseract hOCR output format:** Quality analysis enhancement assumes ocrmypdf can provide hOCR sidecar with word-level confidence. Verify `ocrmypdf --output-type pdfa --sidecar output.txt` provides parseable confidence data in development environment before Phase 2.

- **Hunspell dictionary availability:** Dictionary validation assumes hunspell dictionaries for eng/fra/deu/lat/ell are available via system package manager or Python package. Verify installation path and pyenchant/hunspell bindings before Phase 2 implementation.

- **Resource budgeting parameters:** Optimal ProcessPoolExecutor worker count, ocrmypdf --jobs setting, and memory limits need experimental tuning on target hardware during Phase 4. Research provides patterns but not exact numbers.

**Handling during implementation:**
1. **Phase 0 (before Phase 1):** Verify all library versions and update pyproject.toml dependencies
2. **Phase 2 entry:** Verify hOCR format and hunspell availability, adjust design if unavailable
3. **Phase 3 entry:** Verify Marker import paths with current version, create adapter module if API changed
4. **Phase 4 execution:** Benchmark parallel performance, tune worker counts based on actual measurements

## Sources

### Primary (HIGH confidence)
- **Direct codebase analysis** — pipeline.py (600 lines), processor.py (400+ lines), quality.py, cli.py, pyproject.toml. All architectural problems and pitfalls grounded in actual code bugs, not theory.
- **Python standard library docs** — concurrent.futures.ProcessPoolExecutor, multiprocessing pickling constraints, context managers
- **PyMuPDF documentation** — fitz API for file handle management, page extraction/insertion
- **Python packaging best practices** — PEP 517, src layout, library/CLI separation patterns

### Secondary (MEDIUM confidence)
- **Training data knowledge (May 2025 cutoff)** — Library versions (ocrmypdf 16.x, marker-pdf 1.x, PyMuPDF 1.24.x), API patterns for ocrmypdf/Marker/hunspell. Core choices sound but versions need verification.
- **Domain expertise in OCR quality assessment** — Multi-signal quality analysis, quality scoring weights, academic text patterns. No web verification available.
- **PyTorch multiprocessing constraints** — CUDA context not shareable across fork, model pickling limitations. Well-established but not verified against current PyTorch version.

### Tertiary (LOW confidence, needs validation)
- **Tesseract hOCR confidence output** — Assumption that ocrmypdf preserves per-word confidence via sidecar. Needs verification in development environment.
- **Marker API stability** — Import paths and model loading API may have changed since training data cutoff. Must verify current version.
- **Optimal resource budgeting parameters** — Worker counts, memory limits, performance characteristics need experimental validation on target hardware.

---
*Research completed: 2026-01-28*
*Ready for roadmap: yes*
