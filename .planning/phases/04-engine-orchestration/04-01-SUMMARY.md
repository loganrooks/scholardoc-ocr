# Phase 4 Plan 1: Pipeline Rewrite Summary

**One-liner:** Rewrote pipeline.py with per-file Surya batching, .txt writeback, and BatchResult return type using Phase 2-3 backend modules.

## What Was Done

### Task 1: Rewrite pipeline.py with per-file Surya and writeback
- Replaced entire pipeline.py with new orchestration using `tesseract.run_ocr()` and `surya.convert_pdf()` backend modules
- Fixed BUG-01: Surya results now written back to output `.txt` files
- Fixed BUG-02: Surya text extracted from `convert_pdf()` markdown output, not re-read from original PDF
- Added `force_surya` flag to `PipelineConfig`
- Resource-aware worker calculation: `jobs_per_file = cores / files`, `pool_workers = cores / jobs_per_file`
- Per-file try/except in Surya phase ensures one failure doesn't lose other files
- Returns `BatchResult` with `FileResult` per file and `PageResult` per page
- Removed `ExtendedResult`, `_process_single`, `combine_pages_from_multiple_pdfs`, `run_surya_batch`

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Surya markdown placed at first flagged page slot | Surya returns one combined markdown for all requested pages; subsequent slots cleared to avoid duplication |
| Lazy surya import in run_pipeline | Avoids loading torch/ML deps unless Surya phase is actually reached |

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Hash | Message |
|------|---------|
| 2ca02c1 | feat(04-01): rewrite pipeline with per-file Surya and writeback |

## Verification Results

- `ruff check`: All checks passed
- Import test: OK
- ExtendedResult references: 0
- combine_pages references: 0
- run_surya_batch references: 0
- surya.convert_pdf references: 1
- BatchResult references: 5
- force_surya references: 4

## Files Modified

- `src/scholardoc_ocr/pipeline.py` — Complete rewrite (262 insertions, 317 deletions)
