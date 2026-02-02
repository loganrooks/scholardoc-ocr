# Project Research Summary

**Project:** scholardoc-ocr v2.0
**Domain:** Academic OCR pipeline — post-processing, production robustness, MCP resilience
**Researched:** 2026-02-02
**Confidence:** HIGH

## Executive Summary

scholardoc-ocr v2.0 is a production-hardening and text-quality milestone. The v1.0 rearchitecture (library API, multi-signal quality, structured results) is complete. What is missing is everything after OCR: text post-processing to make output RAG-ready (dehyphenation, unicode normalization, line break cleanup, punctuation normalization), structured multiprocess logging, environment validation, timeout protection, work directory cleanup, and async MCP job handling. These are all well-understood problems with established stdlib solutions.

The key insight from research: **zero new production dependencies are needed.** Every v2.0 feature maps to Python stdlib modules -- `unicodedata` for NFC normalization, `logging.handlers.QueueHandler` for multiprocess logging, `shutil.which` for environment validation, `asyncio` for MCP async jobs. Three new files (`postprocess.py`, `logging_config.py`, `environment.py`) plus modifications to `pipeline.py` and `mcp_server.py` cover the entire scope.

The primary risk is text post-processing destroying academic content. Dehyphenation must distinguish soft hyphens U+00AD (always remove) from hard hyphens U+002D (dictionary-check before removing). Philosophical terms ("Merleau-Ponty", "Selbstbewusstsein"), footnote references, and Greek transliterations must survive processing. Unicode normalization (NFC) must be applied first, before all other transforms, to ensure consistent representation across Tesseract and Surya outputs. A secondary risk is that worker process logs are currently silently lost on macOS due to the `spawn` start method -- this must be fixed before adding more complex pipeline stages.

## Key Findings

### Recommended Stack

No new production dependencies. All features use Python stdlib: `unicodedata` for NFC normalization, `logging.handlers.QueueHandler/QueueListener` for multiprocess logging, `shutil.which` + `importlib.metadata` for environment validation, `asyncio` for MCP async jobs. Only potential dev dependency addition: `pytest-asyncio` for testing async MCP tools.

**Core technologies (all stdlib):**
- `unicodedata` + `re`: Text post-processing (NFC normalization, dehyphenation, line breaks)
- `logging.handlers.QueueHandler/QueueListener`: Multiprocess structured logging via `multiprocessing.Queue`
- `shutil.which` + `importlib.metadata` + `subprocess`: Environment validation
- `asyncio` + `uuid`: MCP async job registry and timeout handling
- `tempfile.TemporaryDirectory`: Work directory isolation and cleanup

**What NOT to add:** structlog (QueueHandler suffices), ftfy (OCR text has layout artifacts not encoding issues), pydantic (dataclasses suffice), celery/dramatiq (single-user tool, dict-based job registry is correct), click (defer CLI rewrite, argparse works for v2.0 scope).

### Expected Features

**Must have (table stakes):**
- Dehyphenation — scanned academic texts are heavily hyphenated; breaks search and RAG
- Unicode normalization (NFC) — Tesseract and Surya produce inconsistent Unicode forms
- Line break normalization — OCR preserves physical line breaks; must rejoin paragraphs
- Punctuation normalization — mixed curly/straight quotes, dash variants
- Environment validation — missing tesseract/ghostscript produces cryptic errors in workers
- JSON metadata output — programmatic consumers need structured quality/engine/timing data
- Structured multiprocess logging — worker logs currently lost on macOS (spawn start method)
- Work directory cleanup — intermediate files accumulate GBs across runs

**Should have (differentiators):**
- MCP async job handling — long OCR jobs (5-30 min) block MCP clients
- Timeout handling per file — one corrupt PDF hangs entire pipeline indefinitely
- Configurable post-processing pipeline — different consumers want different normalizations
- Per-page engine provenance in JSON output — auditing which engine produced each page

**Defer to v3.0:**
- Header/footer stripping (medium complexity, needs heuristic tuning)
- Footnote separator detection (high complexity, needs layout analysis)
- Language-aware dehyphenation (layer on top of basic dehyphenation)

### Architecture Approach

All v2.0 features integrate through the existing `run_pipeline(config, callback)` entry point. Three new modules are independent units with zero cross-dependencies, then wired into pipeline.py in a single integration pass. Post-processing is a stateless `str -> str` composable transform chain. Logging uses ProcessPoolExecutor's `initializer` parameter to configure workers. MCP async adds new tools alongside existing `ocr()` for backward compatibility.

**New modules:**
1. `postprocess.py` — `TextPostProcessor` with composable transforms: NFC -> ligatures -> soft hyphens -> line breaks -> dehyphenation -> punctuation. Config dataclass matches existing pattern.
2. `logging_config.py` — `setup_logging()` returns queue + listener. `worker_logging_init()` as ProcessPoolExecutor initializer. JSONFormatter for structured output.
3. `environment.py` — `validate_environment()` checks required binaries eagerly, optional components lazily. Called at entry points (CLI, MCP), never inside pipeline.

**Integration points:**
- `pipeline.py`: Post-process text after OCR before writing .txt. Worker init for logging. Cleanup work dir on success. Write per-file .json metadata.
- `mcp_server.py`: Async job tools (ocr_async, ocr_status, ocr_jobs). Environment validation on first call. Remove `_log()` bypass.
- `types.py`: Add `PostProcessConfig` dataclass. Add `keep_work_dir` to `PipelineConfig`.

### Critical Pitfalls

1. **Dehyphenation destroys intentional hyphens (#12)** — Distinguish U+00AD (always remove) from U+002D (dictionary-check before removing). Whitelist compound philosophical terms and author names. Never dehyphenate inside citations.
2. **Unicode normalization inconsistency across engines (#13)** — Apply NFC as the very first post-processing step. Decompose ligatures (fi, fl, ffi, ffl). Apply at the engine boundary where Tesseract/Surya text merges.
3. **Worker logs silently lost on macOS (#14)** — `spawn` start method creates fresh interpreters with no logging config. Use `Manager().Queue()` with QueueHandler. Configure via ProcessPoolExecutor initializer, not inherited state.
4. **FastMCP crash on client timeout (#15)** — Use FastMCP `task=True` (v2.14+) instead of raw `asyncio.to_thread`. Send progress notifications to keep connection alive. Set `request_timeout` on constructor.
5. **Work directory collision on concurrent runs (#20)** — Include UUID in work directory paths. Use `tempfile.TemporaryDirectory` for per-run isolation. Critical for MCP concurrent requests.

## Implications for Roadmap

### Phase 1: Foundation (Robustness)
**Rationale:** Zero dependencies on other v2.0 work. Immediate value. Prevents debugging headaches during Phase 2 post-processing development. Fixes the macOS worker logging bug that makes all subsequent debugging impossible.
**Delivers:** Environment validation, structured multiprocess logging, work directory cleanup with per-run isolation, per-file timeout protection.
**Addresses:** Environment validation, structured logging, work dir cleanup, timeout handling (all table stakes).
**Avoids:** Pitfalls #14 (lost worker logs), #18 (QueueHandler infinite loop), #19 (over-eager validation), #20 (work dir collision), #22 (MCP _log bypass).

### Phase 2: Text Post-Processing Pipeline
**Rationale:** Core value proposition of v2.0. Depends on Phase 1 logging for debugging transform issues in workers. Transform order is strict and each step depends on the previous.
**Delivers:** RAG-ready text output -- dehyphenated, unicode-normalized, paragraph-joined, punctuation-cleaned. Configurable transform chain.
**Addresses:** Unicode normalization, line break normalization, dehyphenation, punctuation normalization, configurable post-processing (table stakes + differentiator).
**Avoids:** Pitfalls #12 (hyphen destruction), #13 (unicode inconsistency), #16 (footnote corruption), #17 (engine line break mismatch), #21 (Greek term mangling), #23 (soft hyphen confusion).

### Phase 3: Output and MCP Integration
**Rationale:** Requires stable pipeline (Phase 1) and complete post-processing (Phase 2). JSON metadata should reflect post-processing status. MCP async wraps the finished pipeline.
**Delivers:** JSON metadata per file and per batch, MCP async job handling (submit/poll/retrieve), CLI --json flag, per-page engine provenance.
**Addresses:** JSON metadata output, MCP async jobs, per-page engine provenance (table stakes + differentiators).
**Avoids:** Pitfalls #15 (FastMCP timeout crash), #20 (concurrent run collision via UUID work dirs from Phase 1).

### Phase Ordering Rationale

- **Phase 1 before Phase 2:** Structured logging is essential for debugging post-processing transforms in worker processes. Work directory isolation prevents corruption during concurrent testing.
- **Phase 2 before Phase 3:** JSON metadata should include post-processing config and status. MCP async wraps the complete pipeline including post-processing.
- **Within Phase 2, transform order is strict:** NFC -> ligature decomposition -> soft hyphen removal -> line break normalization -> dehyphenation -> punctuation. Each step depends on clean output from the previous step.
- **Environment validation and work dir cleanup are independent** within Phase 1 and can be built in parallel.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 2 (post-processing):** Dehyphenation rules for academic texts need careful design and a test corpus. Dictionary integration with existing `DictionarySignal` needs API verification. Soft vs hard hyphen behavior across Tesseract and Surya outputs needs empirical testing.
- **Phase 3 (MCP async):** FastMCP `task=True` API is relatively new (v2.14). Current FastMCP version in pyproject.toml must be checked. May need version bump.

Phases with standard patterns (skip research-phase):
- **Phase 1 (robustness):** QueueHandler, shutil.which, tempfile.TemporaryDirectory, ProcessPoolExecutor initializer are all well-documented stdlib patterns with cookbook examples. No surprises expected.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All stdlib, verified availability in Python 3.11+. Zero dependency risk. |
| Features | MEDIUM-HIGH | OCR post-processing patterns well-established in document digitization. Academic-specific dehyphenation rules need testing with real corpus. |
| Architecture | HIGH | Based on direct codebase analysis. Integration points clearly identified. Existing patterns (config dataclasses, callbacks, to_dict) support clean extension. |
| Pitfalls | HIGH | Grounded in actual codebase bugs (#14 worker logs lost on macOS) and documented library issues (#15 FastMCP crash). Prevention strategies are specific and testable. |

**Overall confidence:** HIGH

### Gaps to Address

- **Dehyphenation dictionary source:** Research recommends using existing `DictionarySignal` but its current API coverage and suitability for dehyphenation lookup needs verification during Phase 2 planning.
- **FastMCP version:** Current pinned version may predate `task=True` support (requires v2.14+). Check pyproject.toml before Phase 3.
- **Test corpus:** No academic PDF test fixtures exist for post-processing validation. Need synthetic PDFs with known hyphenation patterns, mixed unicode, footnote markers, Greek/German philosophical terms.
- **Manager().Queue() vs multiprocessing.Queue:** PITFALLS.md says use `Manager().Queue()` for pool workers; ARCHITECTURE.md says `multiprocessing.Queue`. The correct answer depends on whether ProcessPoolExecutor uses `spawn`. Needs verification during Phase 1 implementation.
- **Surya line break conventions:** PITFALLS.md #17 notes Surya/Marker outputs markdown-style line breaks vs Tesseract plain text. The exact format difference needs empirical testing to write correct normalization rules.

## Sources

### Primary (HIGH confidence)
- Python 3.11 stdlib documentation (unicodedata, logging.handlers, shutil.which, asyncio, tempfile)
- Direct codebase analysis of pipeline.py, processor.py, quality.py, mcp_server.py, types.py
- Tesseract soft hyphen behavior (GitHub issue #2161)
- FastMCP v2.14 release notes (background tasks), FastMCP issues #823, #864

### Secondary (MEDIUM confidence)
- OCR post-processing patterns from document digitization field (Apache Tika, ABBYY, Tesseract community)
- Python multiprocessing logging guides (SigNoz, Python logging cookbook)
- MCP timeout handling patterns (mcpcat.io)

---
*Research completed: 2026-02-02*
*Ready for roadmap: yes*
