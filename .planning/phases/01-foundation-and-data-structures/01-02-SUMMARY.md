---
phase: 01-foundation-and-data-structures
plan: 02
subsystem: core-library
tags: [cleanup, context-managers, rich-removal, type-safety]
dependency-graph:
  requires: []
  provides: [clean-processor, clean-pipeline, library-ready-code]
  affects: [01-03, 02-01]
tech-stack:
  added: []
  patterns: [context-manager-for-resources]
key-files:
  created: []
  modified:
    - src/scholardoc_ocr/processor.py
    - src/scholardoc_ocr/pipeline.py
    - src/scholardoc_ocr/__init__.py
decisions: []
metrics:
  duration: ~2m
  completed: 2026-01-28
---

# Phase 01 Plan 02: Code Cleanup Summary

**One-liner:** Context managers for fitz, Rich removal from library, dead code deletion, type fix, Levinas->ScholarDoc rename

## What Was Done

### Task 1: processor.py cleanup
- Added `_open_pdf` context manager wrapping all PyMuPDF document open/close operations
- Refactored 6 methods to use context managers: `extract_text`, `extract_text_by_page`, `extract_pages`, `replace_pages`, `get_page_count`, `combine_pages_from_multiple_pdfs`
- Deleted dead `run_surya_on_pages` method (49 lines) -- pipeline uses `run_surya_batch` instead
- Fixed type annotation: `callable` -> `Callable[[str, int, int], None] | None` with proper import
- Removed unused imports (`shutil`, `os`)

### Task 2: pipeline.py and __init__.py cleanup
- Removed all Rich imports (Console, Panel, Progress, Table, Live)
- Removed `console = Console()` global
- Removed `_print_debug_info` function (Rich-dependent presentation, 39 lines)
- Removed Rich Live displays (status tables, progress bars) from `run_pipeline`
- Replaced all `console.print()` calls with `logger.info/warning/error` calls
- Renamed "LEVINAS OCR PIPELINE" to "ScholarDoc OCR Pipeline"
- Updated default `output_dir` from `levinas_ocr` to `scholardoc_ocr`
- Updated `__init__.py` docstring from Levinas to ScholarDoc

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Unused imports in processor.py**
- **Found during:** Task 1
- **Issue:** `shutil` and `os` imports were unused (pre-existing ruff violations)
- **Fix:** Removed both unused imports
- **Commit:** 9928710

**2. [Rule 1 - Bug] Line too long in processor.py**
- **Found during:** Task 1
- **Issue:** Line 294 exceeded 100 char limit (pre-existing)
- **Fix:** Wrapped to multiple lines
- **Commit:** 9928710

**3. [Rule 3 - Blocking] Import sort in pipeline.py**
- **Found during:** Task 2
- **Issue:** Moving `defaultdict` import to top-level caused import block sort violation
- **Fix:** Ran `ruff check --fix`
- **Commit:** 3f1faae

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | 9928710 | refactor(01-02): add context managers and clean up processor.py |
| 2 | 3f1faae | refactor(01-02): remove Rich from pipeline.py, update naming |

## Verification Results

- All imports succeed without Rich installed
- Zero Rich references in pipeline.py and processor.py
- Zero `run_surya_on_pages` references in codebase
- ruff passes on all modified files
- No `sys.exit()` or `raise SystemExit` in library code
- No lowercase `callable` type hints
- No "Levinas" references in modified files
