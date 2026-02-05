# Project Milestones: scholardoc-ocr

## v2.1 Performance (Shipped: 2026-02-04)

**Delivered:** Surya optimization for Apple Silicon with MPS GPU acceleration, model caching, and cross-file batching. Expected 5-15x improvement for multi-file jobs.

**Phases completed:** 11-14 (17 plans total)

**Key accomplishments:**

- Benchmarking infrastructure with pytest-benchmark, GPU-synchronized timing, hardware profiles (M1/M2/M3/M4), and CI regression detection
- MPS device configuration with automatic detection (CUDA > MPS > CPU), validation, and actionable error messages
- GPU-to-CPU fallback: Pipeline automatically retries on CPU when MPS fails, with --strict-gpu override
- Model caching with TTLCache (30 min default), eliminating 30-60s model load time on subsequent MCP requests
- Cross-file batching: All flagged pages across N files processed in single Surya call with memory-aware batch splitting
- Memory optimization: Adaptive batch sizing based on available RAM, cleanup between documents, ocr_memory_stats MCP tool

**Stats:**

- 53 files created/modified (10,180 insertions, 312 deletions)
- 4,465 lines of Python (library)
- 4 phases, 17 plans, 22 requirements
- 8 days from milestone start to ship

**Git range:** `feat(11-01)` → `docs(14)`

**What's next:** v3.0 — Dictionary-based spell correction, config file support, image preprocessing, per-region quality scoring

---

## v2.0 Post-Processing + Robustness (Shipped: 2026-02-02)

**Delivered:** RAG-ready text output with post-processing pipeline (unicode normalization, dehyphenation, paragraph joining), robust operational behavior (structured logging, environment validation, timeout protection), and structured output formats (JSON metadata, async MCP jobs).

**Phases completed:** 8-10 (8 plans total)

**Key accomplishments:**

- Fork-safe multiprocess logging with QueueHandler/QueueListener for macOS
- Environment validation with actionable error messages at startup
- Full traceback capture in all error paths (no more silent failures)
- Post-processing pipeline: unicode normalization, dehyphenation, paragraph joining, punctuation cleanup
- JSON metadata sidecar files and `--extract-text`/`--json` CLI flags
- Async MCP job handling with `ocr_async`/`ocr_status` and progress reporting

**Stats:**

- 32 files created/modified (3,382 insertions, 281 deletions)
- 4,860 lines of Python (3,078 library + 1,782 tests)
- 3 phases, 8 plans
- 6 days from milestone start to ship

**Git range:** `feat(08-01)` → `docs(10)`

**What's next:** v3.0 — Dictionary-based spell correction, config file support, image preprocessing, per-region quality scoring

---

## v1.0 MVP (Shipped: 2026-02-02)

**Delivered:** Complete rearchitecture of hybrid OCR pipeline with fixed Surya integration, multi-signal quality analysis, clean library API, MCP server, and comprehensive test suite.

**Phases completed:** 1-7 (17 plans total)

**Key accomplishments:**

- Complete rearchitecture from monolithic 4-module codebase into clean library + CLI with proper separation of concerns
- Fixed critical Surya bugs — OCR results now written back to output files (BUG-01, BUG-02)
- Multi-signal quality analysis combining garbled regex, dictionary validation, and Tesseract confidence with German language support
- MCP server integration — OCR callable from Claude Desktop with page_range, extract_text, and output_name
- Comprehensive test suite (79+ tests covering quality, backends, pipeline, integration)
- Clean library API with structured results and callback protocol

**Stats:**

- 101 files created/modified
- 3,731 lines of Python (2,348 library + 1,383 tests)
- 7 phases, 17 plans, 30 requirements
- 6 days from project start to ship

**Git range:** `initial` → `feat(07-01)`

**What's next:** v2.0 — Advanced quality analysis (dictionary validation, n-gram scoring, layout checks) and additional features (domain dictionaries, JSON output, dry-run mode)

---
