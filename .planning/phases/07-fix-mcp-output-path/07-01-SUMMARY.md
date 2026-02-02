# Phase 7 Plan 1: Fix MCP output_path Integration Summary

**One-liner:** Added output_path field to FileResult and populated it at pipeline success paths so MCP extract_text and output_name features work.

## Tasks Completed

| Task | Name | Commit | Status |
|------|------|--------|--------|
| 1 | Add output_path to FileResult | 4169216 | Done |
| 2 | Populate output_path in pipeline | f822261 | Done |

## What Was Done

1. Added `output_path: str | None = None` field to `FileResult` dataclass in `types.py`
2. Added `output_path` to `FileResult.to_dict()` serialization (only when set)
3. Set `output_path=str(pdf_path)` at both success return points in `_tesseract_worker`:
   - Existing text good enough (copies input PDF as-is)
   - Tesseract OCR succeeded
4. Error return points correctly leave `output_path` as `None`

## Key Files Modified

- `src/scholardoc_ocr/types.py` - FileResult output_path field + to_dict serialization
- `src/scholardoc_ocr/pipeline.py` - output_path populated at success return points

## Deviations from Plan

None - plan executed exactly as written.

## Decisions Made

- [07-01]: output_path only included in to_dict() when not None (sparse serialization)
