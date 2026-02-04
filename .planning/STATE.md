# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-03)

**Core value:** Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.
**Current focus:** Phase 12 - Device Configuration

## Current Position

Phase: 12 of 14 (Device Configuration)
Plan: 5/5 complete
Status: Phase complete
Last activity: 2026-02-04 — Completed 12-05-PLAN.md (inference GPU fallback)

Progress: v1.0 [##########] | v2.0 [##########] | v2.1 [########  ] 80%

## Performance Metrics

**Velocity:**
- Total plans completed: 30 (v1.0: 17, v2.0: 8, v2.1: 8)
- Average duration: ~30 min (estimate from previous milestones)
- Total execution time: ~14 hours

**By Phase (v2.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 11. Benchmarking | 5/5 | 17min | 3.4min |
| 12. Device Config | 5/5 | 13min | 2.6min |
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
- MPS sync for Surya timing: Always call mps_sync() before measuring GPU operation duration
- Per-file timing keys: Store surya_model_load and surya_inference in phase_timings dict
- CI benchmark threshold: 150% alert threshold (fail on 50%+ regression)
- macos-14 runner: Apple Silicon for MPS benchmark parity with local dev
- device_used as str|None: Flexible device tracking, omit from JSON when None
- load_models() returns tuple: (model_dict, device_str) for explicit device tracking
- check_gpu_availability() lazy imports torch: Avoids loading ML deps at startup
- strict_gpu enforcement deferred to inference: Flag stored in config, enforced in convert_pdf_with_fallback()
- OOM recovery outside except block: GPU memory cleared after exception handling for proper garbage collection

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

Last session: 2026-02-04
Stopped at: Completed 12-05-PLAN.md (inference GPU fallback) - Phase 12 complete
Resume file: None
