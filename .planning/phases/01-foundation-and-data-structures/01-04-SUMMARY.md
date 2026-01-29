# Phase 1 Plan 4: Callback Wiring Summary

**One-liner:** Wired PipelineCallback protocol into pipeline.py and processor.py with PhaseEvent/ProgressEvent/ModelEvent emissions and integration tests.

## What Was Done

### Task 1: Wire callbacks into pipeline.py and processor.py
- Added `callback: PipelineCallback | None = None` parameter to `run_pipeline()`
- Default to `LoggingCallback()` when no callback provided
- Emit `PhaseEvent` at start/end of Tesseract phase (2 events)
- Emit `ProgressEvent` per file completed in Phase 1 loop
- Emit `PhaseEvent` at start/end of Surya phase (2 events)
- Pass callback to `run_surya_batch()` for model and progress events
- In processor.py: replaced `progress_callback: Callable` with `callback: PipelineCallback`
- Emit `ModelEvent` around `create_model_dict()` (loading/ready)
- Updated `report()` helper to use `callback.on_progress()`

### Task 2: Add callback integration tests
- 8 tests covering protocol compliance, wiring, and event emission
- `CollectorCallback` test helper collects all events for assertions
- Tests verify phase events fire with mocked `_process_single`

## Deviations from Plan

None - plan executed exactly as written.

## Key Files

- `src/scholardoc_ocr/pipeline.py` - Callback-wired pipeline with PhaseEvent/ProgressEvent
- `src/scholardoc_ocr/processor.py` - PipelineCallback in run_surya_batch with ModelEvent
- `tests/test_callbacks.py` - 8 integration tests

## Commits

| Hash | Message |
|------|---------|
| 1129eeb | feat(01-04): wire callbacks into pipeline.py and processor.py |
| 0044825 | test(01-04): add callback integration tests |

## Verification

- All 22 tests pass (8 new callback tests + 14 existing)
- Lint clean on modified files
- Public API exports verified
