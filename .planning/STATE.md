# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-17)

**Core value:** Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.
**Current focus:** v3.0 Diagnostic Intelligence — Phase 15 (Diagnostic Infrastructure)

## Current Position

Phase: 15 of 20 (Diagnostic Infrastructure)
Plan: 3 of 3 in current phase (PHASE COMPLETE)
Status: Phase Complete
Last activity: 2026-02-17 — Completed 15-03-PLAN.md (Diagnostics-Gated Features + JSON Sidecar)

Progress: v1.0 [##########] | v2.0 [##########] | v2.1 [##########] | v3.0 [##░░░░░░░░] ~17%

## Performance Metrics

**Velocity:**
- Total plans completed: 45 (v1.0: 17, v2.0: 8, v2.1: 17, v3.0: 3)
- Average duration: ~4 min/plan
- Total milestones: 3 shipped, 1 in progress

**By Milestone:**

| Milestone | Phases | Plans | Duration |
|-----------|--------|-------|----------|
| v1.0 MVP | 7 | 17 | 6 days |
| v2.0 Robustness | 3 | 8 | 6 days |
| v2.1 Performance | 4 | 17 | 8 days |
| v3.0 Diagnostic Intelligence | 6 | TBD | — |
| Phase 15 P01 | 3min | 2 tasks | 2 files |
| Phase 15 P02 | 4min | 2 tasks | 2 files |
| Phase 15 P03 | 4min | 2 tasks | 3 files |

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.
Recent for v3.0:
- Measure before you fix: instrument and evaluate before making changes
- CLI-based LLM evaluation over API: uses existing accounts, no SDK dependency
- Independent evaluation framework: reusable, not coupled to pipeline execution
- Primitive-only dataclasses for ProcessPoolExecutor pickling safety (Phase 15)
- TYPE_CHECKING imports to avoid circular dependencies between diagnostics and types modules (Phase 15)
- Conservative struggle category thresholds, Phase 19 will calibrate (Phase 15)
- [Phase 15]: Primitive-only dataclasses for ProcessPoolExecutor pickling safety
- [Phase 15]: Postprocess counts approximate per-page (global counts), Phase 19 refines
- [Phase 15]: Error-resilient diagnostics (try/except, fallback to None, never breaks pipeline)
- [Phase 15]: Lazy cv2/numpy import in analyze_image_quality to avoid weight for non-diagnostics runs
- [Phase 15]: 150 DPI page rendering for image quality (4x memory savings vs 300 DPI)
- [Phase 15]: DIAG-04 text preservation timing: capture BEFORE map_results_to_files mutates text

### Pending Todos

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 001 | Remove brittle PATH hacks, document MCP env config | 2026-02-02 | d04dbdd | [001-remove-brittle-path-hacks](./quick/001-remove-brittle-path-hacks/) |
| 002 | Fix MCP tool issues (path guidance, async preference, log rotation) | 2026-02-03 | a66186a | [002-fix-mcp-tool-issues](./quick/002-fix-mcp-tool-issues/) |

### Blockers/Concerns

- Pre-existing test collection error: test_callbacks.py imports removed `ExtendedResult` from pipeline.py

## Session Continuity

Last session: 2026-02-17
Stopped at: Completed 15-03-PLAN.md (Diagnostics-Gated Features + JSON Sidecar) -- Phase 15 COMPLETE
Resume file: None
