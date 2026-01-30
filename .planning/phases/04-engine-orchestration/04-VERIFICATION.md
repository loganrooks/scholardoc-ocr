---
phase: 04-engine-orchestration
verified: 2026-01-29T12:00:00Z
status: passed
score: 6/6 must-haves verified
---

# Phase 4: Engine Orchestration Verification Report

**Phase Goal:** Fix pipeline orchestration to use per-file Surya batching with shared models, eliminate cross-file index mapping, and write Surya results back to output files.

**Verified:** 2026-01-29T12:00:00Z
**Status:** PASSED
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Surya OCR results written back to output files (writeback bug fixed) | ✓ VERIFIED | Lines 361-380 in pipeline.py write Surya markdown to .txt files. Integration test `test_pipeline_surya_writeback` verifies text appears in output. |
| 2 | Surya batch output correctly extracted from rendered markdown (extraction bug fixed) | ✓ VERIFIED | Line 357: `surya_markdown = surya.convert_pdf()` — text comes from convert_pdf return, not re-reading PDF. Comment explicitly marks BUG-02 fix. |
| 3 | Per-file Surya batching eliminates fragile cross-file page index mapping | ✓ VERIFIED | Lines 330-400: Sequential per-file loop, each file processed independently. No `combine_pages` or cross-file combined PDF patterns found. |
| 4 | Resource-aware parallelism coordinates CPU usage (pool workers with ocrmypdf jobs) | ✓ VERIFIED | Lines 237-240: `jobs_per_file = cores / files`, `pool_workers = cores / jobs_per_file`. Integration test verifies calculation logic. |
| 5 | Integration test verifies Surya text actually appears in final output file | ✓ VERIFIED | `test_pipeline_surya_writeback` (lines 179-218 of test_pipeline.py) writes BAD_PAGE to .txt, runs Surya, asserts "SURYA_ENHANCED_TEXT" in updated file. |
| 6 | Pipeline orchestration separated from UI presentation (library vs CLI concerns) | ✓ VERIFIED | cli.py imports and calls `run_pipeline()` (line 192), formats BatchResult via `_print_summary()`. No business logic in CLI. __init__.py exports pipeline API. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/scholardoc_ocr/pipeline.py` | Two-phase orchestration with per-file Surya batching | ✓ VERIFIED | 423 lines. `run_pipeline()` returns BatchResult. Phase 1 (Tesseract) parallel via ProcessPoolExecutor. Phase 2 (Surya) sequential per-file with shared models. |
| `src/scholardoc_ocr/cli.py` | Thin wrapper with --force-surya flag | ✓ VERIFIED | 198 lines. Imports run_pipeline (line 9). --force-surya arg (line 110). Calls pipeline API (line 192), prints summary, exits with proper code. |
| `src/scholardoc_ocr/__init__.py` | Public API exports | ✓ VERIFIED | Exports PipelineConfig, run_pipeline (lines 15, 47-48) in __all__. |
| `tests/test_pipeline.py` | Integration tests including writeback verification | ✓ VERIFIED | 354 lines, 9 tests, all passing. Includes TEST-04 writeback verification test. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| pipeline.py | surya.py | surya.convert_pdf() | ✓ WIRED | Line 357: `surya_markdown = surya.convert_pdf(input_path, model_dict, page_range=bad_indices)`. Lazy import at line 211. |
| pipeline.py | tesseract.py | tesseract.run_ocr() | ✓ WIRED | Worker function line 52: `from .tesseract import run_ocr`. Called at line 124. |
| pipeline.py | types.py | Returns BatchResult | ✓ WIRED | Line 20: import BatchResult. Line 414: `return BatchResult(files=file_results, ...)` |
| cli.py | pipeline.py | run_pipeline() call | ✓ WIRED | Line 9: `from .pipeline import run_pipeline`. Line 192: `batch = run_pipeline(config)` |
| __init__.py | pipeline.py | Exports API | ✓ WIRED | Line 15: `from .pipeline import PipelineConfig, run_pipeline`. In __all__ list. |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| BUG-01 | ✓ SATISFIED | Lines 361-380: Surya text written to .txt files. Test verifies. |
| BUG-02 | ✓ SATISFIED | Line 357: Text from convert_pdf markdown, not re-read. |
| ARCH-01 | ✓ SATISFIED | CLI wraps pipeline API (cli.py line 192). Separation clear. |
| ARCH-02 | ✓ SATISFIED | Per-file Surya loop (lines 330-400). No cross-file patterns. |
| ARCH-04 | ✓ SATISFIED | Resource calculation (lines 237-240). Verified by tests. |
| TEST-03 | ✓ SATISFIED | 9 integration tests in test_pipeline.py, all passing. |
| TEST-04 | ✓ SATISFIED | test_pipeline_surya_writeback verifies Surya text in output. |

### Anti-Patterns Found

**No blocker anti-patterns detected.**

Scan results:
- TODO/FIXME comments: 0
- Placeholder content: 0
- Empty implementations: 0
- Console.log only: 0
- print() statements in library code: 0

✓ Clean implementation with no stub patterns.

### Verification Checklist

**Code Structure:**
- [x] PipelineConfig has force_surya field (line 35, defaults to False)
- [x] run_pipeline() returns BatchResult (line 414)
- [x] ExtendedResult eliminated (0 references found)
- [x] combine_pages patterns eliminated (0 references found)
- [x] Surya models loaded once, shared across files (line 325)
- [x] Per-file try/except for Surya failures (lines 331-400)

**Bug Fixes:**
- [x] BUG-01: Writeback code exists (lines 361-380)
- [x] BUG-01: Integration test verifies writeback
- [x] BUG-02: Markdown extraction from convert_pdf (line 357)
- [x] BUG-02: No re-reading original PDF for Surya text

**Architecture:**
- [x] Phase 1 parallel Tesseract (ProcessPoolExecutor line 266)
- [x] Phase 2 sequential per-file Surya (for loop line 330)
- [x] Resource-aware worker calculation (lines 237-240)
- [x] CLI wraps pipeline API (cli.py line 192)
- [x] Pipeline API exported from package (__init__.py line 15)

**Testing:**
- [x] 9 integration tests exist
- [x] All tests passing
- [x] Writeback test included (test_pipeline_surya_writeback)
- [x] Partial failure test included
- [x] force_surya test included
- [x] Resource calculation tests included

**Import/Lint:**
- [x] ruff check passes (no errors)
- [x] Package imports successfully
- [x] PipelineConfig and run_pipeline importable from package top-level

---

## Summary

**ALL PHASE 4 SUCCESS CRITERIA MET.**

The phase goal is fully achieved:

1. **BUG-01 FIXED:** Surya results now written to output .txt files (lines 361-380), verified by integration test
2. **BUG-02 FIXED:** Surya text extracted from convert_pdf markdown output (line 357), not re-read from original
3. **Per-file batching:** Sequential per-file Surya processing eliminates cross-file page mapping complexity
4. **Resource-aware parallelism:** Dynamic worker/jobs calculation coordinates CPU usage (lines 237-240)
5. **Integration tests:** 9 comprehensive tests including writeback verification (TEST-04)
6. **Architecture separation:** CLI is thin wrapper, pipeline API cleanly exported for library use

The codebase implements exactly what was planned:
- pipeline.py completely rewritten (423 lines)
- Per-file Surya processing with shared models
- Proper error handling (per-file try/except)
- Clean separation between orchestration (pipeline.py) and presentation (cli.py)
- Comprehensive test coverage

**No gaps found. Phase 4 complete.**

---

_Verified: 2026-01-29T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
