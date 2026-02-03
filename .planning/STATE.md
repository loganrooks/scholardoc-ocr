# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-03)

**Core value:** Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.
**Current focus:** Phase 11 - Benchmarking Foundation

## Current Position

Phase: 11 of 14 (Benchmarking Foundation)
Plan: 01, 02, 03 of 6 complete
Status: In progress
Last activity: 2026-02-03 — Completed 11-02-PLAN.md (Benchmark Tests)

Progress: v1.0 [##########] | v2.0 [##########] | v2.1 [###       ] 25%

## Performance Metrics

**Velocity:**
- Total plans completed: 25 (v1.0: 17, v2.0: 8)
- Average duration: ~30 min (estimate from previous milestones)
- Total execution time: ~12.5 hours

**By Phase (v2.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 11. Benchmarking | 3/6 | 13min | 4.3min |
| 12. Device Config | - | - | - |
| 13. Model Caching | - | - | - |
| 14. Batching | - | - | - |

*Updated after each plan completion*

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

Recent decisions affecting v2.1:
- Benchmarking first: Establish baseline before any optimization changes
- Research-driven phase order: BENCH -> DEV -> MODEL -> BATCH (from research findings)
- MIXED enum ordering: Placed between EXISTING and NONE for semantic ordering (active engines first)
- Engine aggregation: compute_engine_from_pages() ignores NONE pages when computing aggregate
- Lazy torch imports: Avoid loading ML dependencies at module import time
- Session-scoped fixtures: Share loaded models across entire benchmark test session
- Pedantic mode for GPU benchmarks: rounds=3/warmup=0 for cold start, rounds=5/warmup=1 for inference
- Hardware profile grouping: benchmark-group-by=param:hardware_profile,func for BENCH-05 baselines

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

Last session: 2026-02-03
Stopped at: Completed 11-02-PLAN.md (Benchmark Tests)
Resume file: None
