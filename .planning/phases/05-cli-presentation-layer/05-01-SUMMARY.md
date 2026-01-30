# Phase 5 Plan 1: Language Configuration and File Discovery Fix Summary

**One-liner:** LANGUAGE_MAP with ISO 639-1 resolution plus PipelineConfig language fields and recursive path fix

## What Was Done

### Task 1: Add language mapping and PipelineConfig language fields
- Added `LANGUAGE_MAP` dict and `resolve_languages()` helper to `types.py`
- Added `langs_tesseract` and `langs_surya` fields to `PipelineConfig` with sensible defaults
- Replaced hardcoded language list in `config_dict` with config values
- Passed `SuryaConfig` with user-specified languages to `surya.convert_pdf()`
- Exported new symbols from `__init__.py`
- **Commit:** 93f3336

### Task 2: Fix recursive file discovery bug
- Changed `p.name` to `str(p.relative_to(input_dir))` in both `rglob` and `glob` calls
- Files in subdirectories now preserve their relative paths
- **Commit:** 3c98cb8

## Deviations from Plan

None - plan executed exactly as written.

## Key Files

### Created
- (none)

### Modified
- `src/scholardoc_ocr/types.py` — LANGUAGE_MAP, resolve_languages()
- `src/scholardoc_ocr/pipeline.py` — PipelineConfig language fields, config propagation
- `src/scholardoc_ocr/cli.py` — recursive file discovery fix
- `src/scholardoc_ocr/__init__.py` — exports

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| ValueError on unknown language codes | Fail fast rather than silently ignore |
| Default languages include German (deu/de) | Academic philosophy texts often contain German |

## Verification

- `resolve_languages(['en','fr'])` returns `('eng,fra', 'en,fr')`
- `resolve_languages([])` returns full defaults
- `PipelineConfig()` defaults include all 5 languages
- Recursive discovery preserves subdirectory paths
- `ruff check` passes on all modified files
- Pre-existing test collection error in test_callbacks.py (imports removed `ExtendedResult`) - not related to this plan

## Next Phase Readiness

Plan 05-02 can now use `resolve_languages()` to convert CLI language args and pass them to `PipelineConfig.langs_tesseract` / `langs_surya`. The recursive file discovery bug is fixed.
