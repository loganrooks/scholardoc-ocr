# Phase 10 Plan 01: Structured Output Formats Summary

**One-liner:** JSON metadata sidecar files, --extract-text for .txt persistence, --json for stdout structured output

## What Was Done

### Task 1: JSON metadata file + extract_text config control
- Added `extract_text: bool = False` to `PipelineConfig`
- Added JSON metadata writing after Phase 2 (Surya) completes: writes `{stem}.json` alongside each output PDF in `final/`
- Added .txt cleanup step: removes .txt files from `final/` unless `extract_text=True`
- Updated two tests that read .txt files to set `extract_text=True`

### Task 2: --extract-text and --json CLI flags
- Added `--extract-text` flag to argparse
- Added `--json` flag (dest=`json_output`) to argparse
- `--json` uses `LoggingCallback` instead of `RichCallback`, prints `BatchResult.to_json()` to stdout
- Error handling outputs JSON when `--json` is set

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated tests expecting .txt files in final/**
- **Found during:** Task 1
- **Issue:** Two tests (`TestSuryaWriteback`, `TestSuryaPartialFailure`) read .txt files from final/ which are now cleaned up by default
- **Fix:** Added `extract_text=True` to those tests' config construction
- **Files modified:** tests/test_pipeline.py
- **Commit:** 709ab6a

## Verification

- `ruff check src/` passes
- 118 tests pass (excluding pre-existing test_callbacks.py import error)
- `ocr --help` shows both `--extract-text` and `--json` flags
- `json.dumps` present in pipeline.py
- `extract_text` and `json_output` present in cli.py

## Key Files

- `src/scholardoc_ocr/pipeline.py` - JSON metadata writing, extract_text control
- `src/scholardoc_ocr/cli.py` - Two new CLI flags
- `src/scholardoc_ocr/types.py` - Existing `BatchResult.to_json()` used by --json

## Commits

| Hash | Message |
|------|---------|
| 709ab6a | feat(10-01): JSON metadata files and extract_text config control |
| 3a6d7a7 | feat(10-01): add --extract-text and --json CLI flags |

## Duration

~3 minutes
