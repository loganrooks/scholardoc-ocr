---
phase: 12-device-configuration
plan: 05
type: summary
subsystem: surya-inference
tags: [gpu, fallback, mps, cuda, cpu, error-handling]

dependency-graph:
  requires: [12-03, 12-04]
  provides: [convert_pdf_with_fallback, inference-fallback]
  affects: []

tech-stack:
  added: []
  patterns: [gpu-cpu-fallback, oom-recovery]

key-files:
  created: []
  modified:
    - src/scholardoc_ocr/surya.py
    - src/scholardoc_ocr/pipeline.py
    - tests/test_device.py

decisions:
  - id: DEV-05-1
    summary: OOM recovery outside except block
    rationale: GPU memory must be cleared after exception handling completes to allow garbage collection

metrics:
  duration: 3min
  completed: 2026-02-04
---

# Phase 12 Plan 05: Inference-Time GPU Fallback Summary

GPU-to-CPU inference fallback with OOM recovery via convert_pdf_with_fallback(), integrated into pipeline with strict_gpu control.

## Completed Tasks

| # | Task | Commit | Files Changed |
|---|------|--------|---------------|
| 1 | Add convert_pdf_with_fallback to surya.py | 7e0ea1e | src/scholardoc_ocr/surya.py |
| 2 | Update pipeline to use convert_pdf_with_fallback | ceefc5b | src/scholardoc_ocr/pipeline.py |
| 3 | Add tests for inference fallback | 6ae2525 | tests/test_device.py |

## Key Implementation Details

### convert_pdf_with_fallback Function

```python
def convert_pdf_with_fallback(
    input_path: Path,
    model_dict: dict[str, Any],
    config: SuryaConfig | None = None,
    page_range: list[int] | None = None,
    strict_gpu: bool = False,
) -> tuple[str, bool]:
```

**Return value:** `(markdown_text, fallback_occurred)`

**Fallback logic:**
1. Attempt GPU conversion via `convert_pdf()`
2. On `RuntimeError` (MPS bugs, OOM):
   - If `strict_gpu=True`: Raise `SuryaError` immediately
   - If `strict_gpu=False`: Clear GPU memory, reload models on CPU, retry
3. OOM recovery happens OUTSIDE except block (critical for garbage collection)

### Pipeline Integration

- Replaced `surya.convert_pdf()` with `surya.convert_pdf_with_fallback()`
- Passes `config.strict_gpu` from PipelineConfig
- On fallback:
  - Logs warning with filename
  - Updates `file_result.device_used = "cpu"`
  - Sets `file_result.phase_timings["surya_fallback"] = True`

### Test Coverage

5 new tests in `TestConvertPdfWithFallback`:
- Function exists and is callable
- Falls back to CPU on GPU failure (mock)
- `strict_gpu=True` raises `SuryaError`
- Successful GPU returns `(markdown, False)`
- Return type is `tuple[str, bool]`

## Deviations from Plan

None - plan executed exactly as written.

**Note:** The `strict_gpu` field in PipelineConfig and CLI `--strict-gpu` flag were already present in uncommitted changes from 12-04, which this plan depends on.

## Decisions Made

| ID | Decision | Rationale |
|----|----------|-----------|
| DEV-05-1 | OOM recovery outside except block | GPU memory (MPS/CUDA caches) must be cleared after exception handling completes. Doing this inside the except block prevents proper garbage collection of GPU tensors. |

## Verification Results

```
ruff check: All checks passed!
ruff format: 2 files already formatted
pytest test_device.py: 29 passed, 2 skipped
pytest test_pipeline.py: 11 passed
```

## Phase 12 Progress

- 12-01: Device detection module (COMPLETE)
- 12-02: Timing utilities (COMPLETE)
- 12-03: Device integration in surya/pipeline (COMPLETE)
- 12-04: CLI --strict-gpu and startup diagnostics (uncommitted changes present)
- 12-05: Inference-time GPU fallback (COMPLETE)

## Next Phase Readiness

Phase 12 is complete pending 12-04 summary documentation. All device configuration functionality is implemented:

- DEV-01: Automatic device detection (12-01, 12-02, 12-03)
- DEV-02: Startup validation with actionable messages (12-04)
- DEV-03: Automatic CPU fallback on failure (12-05)
- DEV-04: Full-CPU fallback strategy (12-05, via whole-batch retry)

**Ready for:** Phase 13 (Model Caching) once 12-04 is finalized.
