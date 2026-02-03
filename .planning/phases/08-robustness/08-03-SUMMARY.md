# Phase 08 Plan 03: Full Traceback Capture Summary

**One-liner:** Added exc_info=True and traceback.format_exc() to all except blocks in pipeline.py and processor.py, eliminating silent error swallowing.

## Tasks Completed

| Task | Name | Commit | Status |
|------|------|--------|--------|
| 1 | Fix all error handling paths to capture full tracebacks | 06b6842 | Done |

## Changes Made

### pipeline.py
- Added `import traceback` at module top
- `_tesseract_worker` catch-all (line ~191): Added `logger.error(..., exc_info=True)` and `traceback.format_exc()` in error field
- `future.result()` failure (line ~296): Changed `error=str(e)` to `error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}"`, added `exc_info=True`
- Surya fallback failure (line ~408): Added `exc_info=True` to logger.warning

### processor.py
- Fixed 4 f-string logger calls to use %-formatting (ruff-compatible)
- Added `exc_info=True` to all 5 except blocks
- Added logging to previously silent `get_page_count()` except block

### surya.py
- No changes needed: all except blocks already re-raise as SuryaError with `from exc`, preserving full chain

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Silent except in get_page_count()**
- **Found during:** Task 1 audit
- **Issue:** `except Exception: return 0` silently swallowed errors with no logging
- **Fix:** Added `logger.warning("Failed to get page count for %s", pdf_path, exc_info=True)`

**2. [Rule 1 - Bug] f-string logger calls in processor.py**
- **Found during:** Task 1 audit
- **Issue:** Logger calls used f-strings (`f"...{e}"`) instead of %-formatting, defeating lazy evaluation
- **Fix:** Converted to `logger.warning("...: %s", e, exc_info=True)` format

## Verification

- `ruff check` passes on all three files
- Module imports verified successfully
- No bare `str(e)` remains in except blocks

## Duration

~3 minutes
