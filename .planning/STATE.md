# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-03)

**Core value:** Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.
**Current focus:** Phase 14 - Cross-file Batching — IN PROGRESS

## Current Position

Phase: 14 of 14 (Cross-file Batching)
Plan: 2/3 complete
Status: In progress
Last activity: 2026-02-05 — Completed 14-02-PLAN.md (cross-file page batching)

Progress: v1.0 [##########] | v2.0 [##########] | v2.1 [##########] 97%

## Performance Metrics

**Velocity:**
- Total plans completed: 35 (v1.0: 17, v2.0: 8, v2.1: 13)
- Average duration: ~30 min (estimate from previous milestones)
- Total execution time: ~14.6 hours

**By Phase (v2.1):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 11. Benchmarking | 5/5 | 17min | 3.4min |
| 12. Device Config | 5/5 | 13min | 2.6min |
| 13. Model Caching | 3/3 | 16min | 5.3min |
| 14. Batching | 2/3 | 9min | 4.5min |

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
- TTLCache maxsize=1: Only one model set cached at a time (Surya models too large for multiple)
- 30 minute default TTL: Balance between memory retention and reload frequency
- SCHOLARDOC_MODEL_TTL env var: Runtime TTL override without code changes
- Load outside lock pattern: Model loading (30-60s) doesn't block other threads
- Cache integration at run_pipeline level: Single cache lookup per pipeline run
- Cleanup after success only: cleanup_between_documents() called after Surya completes
- ModelCache mock pattern: Mock at scholardoc_ocr.model_cache module level for tests
- MCP lifespan for warm loading: SCHOLARDOC_WARM_LOAD=true env var triggers pre-loading at startup
- Memory stats via MCP tool: ocr_memory_stats returns device, allocated_mb, reserved_mb, cache_ttl_seconds
- psutil for memory detection: Cross-platform, lightweight, already common in Python ecosystem
- Memory tier boundaries: 8GB (conservative), 16GB (moderate), 32GB+ (aggressive) for batch sizing
- setdefault pattern for batch sizes: Allows user env var overrides without code changes
- Heuristic text splitting: Horizontal rules + triple newlines, fallback to first-page assignment
- batch_index sequential assignment: Enables direct mapping from combined PDF back to sources
- Single Surya call per batch: N files with flagged pages -> 1 Surya invocation
- Cleanup per batch not per file: GPU memory freed once after entire batch completes

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

Last session: 2026-02-05
Stopped at: Completed 14-02-PLAN.md, ready for 14-03
Resume file: None
