# Phase 10 Plan 02: Async MCP Jobs and Progress Reporting Summary

**One-liner:** ocr_async/ocr_status tools with JobState store, TTL cleanup, and ctx.info progress on synchronous ocr()

## Tasks Completed

| # | Task | Commit | Key Files |
|---|------|--------|-----------|
| 1 | Async job store and ocr_async/ocr_status tools | 37d8252 | src/scholardoc_ocr/mcp_server.py |
| 2 | Progress reporting on synchronous ocr() tool | 341f9b1 | src/scholardoc_ocr/mcp_server.py |

## What Was Built

### Async Job Infrastructure
- `JobState` dataclass tracks job_id, status (running/completed/failed), progress dict, result, error, and created_at timestamp
- Module-level `_jobs` dict stores active jobs
- `_cleanup_expired_jobs()` removes completed/failed jobs older than 1 hour TTL
- `_JobProgressCallback` bridges pipeline callbacks to JobState.progress dict

### ocr_async Tool
- Accepts same params as ocr() (minus page_range/output_name for simplicity)
- Builds PipelineConfig, creates JobState with uuid4, spawns asyncio.create_task
- Returns `{"job_id": ..., "status": "running"}` immediately

### ocr_status Tool
- Looks up job by ID, returns full state including progress and result
- Calls cleanup on each invocation

### Synchronous ocr() Progress
- Added MCP Context parameter, reports start and completion via `ctx.info()`
- Comment documents why mid-pipeline progress is not feasible (thread boundary)

### extract_text Fix
- Removed PyMuPDF re-extraction that lost post-processing transforms
- Now uses pipeline's .txt output files (preserves dehyphenation, paragraph joining)
- Sets `config.extract_text = True` so pipeline preserves .txt files

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed extract_text losing post-processing transforms**
- **Found during:** Task 2
- **Issue:** Old code re-extracted text from PDF via PyMuPDF, discarding dehyphenation and paragraph joining done by the pipeline's postprocess module
- **Fix:** Use pipeline's already-written .txt files instead; set config.extract_text=True
- **Files modified:** src/scholardoc_ocr/mcp_server.py
- **Commit:** 341f9b1

## Verification

- ruff check passes
- Import succeeds without errors
- 118 tests pass (pre-existing test_callbacks.py import error excluded)
