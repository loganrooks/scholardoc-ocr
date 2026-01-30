---
phase: 04-engine-orchestration
plan: 02
subsystem: cli
tags: [argparse, cli, pipeline-api, batch-result]

requires:
  - phase: 04-01
    provides: "PipelineConfig, run_pipeline, BatchResult pipeline API"
provides:
  - "CLI with --force-surya flag and BatchResult summary display"
  - "Package-level exports of PipelineConfig and run_pipeline"
affects: [04-03, 05-testing]

tech-stack:
  added: []
  patterns: ["thin CLI wrapper over library API"]

key-files:
  created: []
  modified:
    - src/scholardoc_ocr/cli.py
    - src/scholardoc_ocr/__init__.py

key-decisions:
  - "CLI only prints final summary, not inline progress (callbacks handle that)"
  - "No-files-found exits with code 1 via sys.exit"

patterns-established:
  - "CLI as presentation-only layer: parse args, call run_pipeline, print summary, set exit code"

duration: 2min
completed: 2026-01-29
---

# Phase 4 Plan 2: CLI Update and Pipeline API Export Summary

**CLI updated as thin wrapper with --force-surya flag, BatchResult summary formatting, and pipeline API exported from package**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-29
- **Completed:** 2026-01-29
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- CLI is now a thin presentation layer wrapping run_pipeline()
- Added --force-surya flag separate from --force (Tesseract)
- Structured _print_summary() formats BatchResult with per-file and debug per-page output
- Exit code 0 on success, 1 on errors
- PipelineConfig and run_pipeline exported from package __init__.py for library usage

## Task Commits

1. **Task 1: Update CLI with --force-surya and BatchResult formatting** - `65db1f6` (feat)
2. **Task 2: Export pipeline API from package __init__.py** - `96e9e34` (feat)

## Files Created/Modified
- `src/scholardoc_ocr/cli.py` - CLI with --force-surya, _print_summary(), exit codes
- `src/scholardoc_ocr/__init__.py` - Added PipelineConfig, run_pipeline exports

## Decisions Made
- CLI prints only final summary; inline progress is handled by pipeline callbacks
- No-files-found case uses sys.exit(1) instead of bare return

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Import sorting lint error in __init__.py after adding pipeline import; auto-fixed with ruff --fix

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CLI and library API ready for integration testing in 04-03
- All pipeline types, callbacks, and API exported from package

---
*Phase: 04-engine-orchestration*
*Completed: 2026-01-29*
