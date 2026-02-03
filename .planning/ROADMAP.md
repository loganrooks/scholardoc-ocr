# Roadmap: scholardoc-ocr

## Milestones

- v1.0 MVP - Phases 1-7 (shipped 2026-02-02)
- v2.0 Post-Processing + Robustness - Phases 8-10 (shipped 2026-02-02)
- v2.1 Performance - Phases 11-14 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-7) - SHIPPED 2026-02-02</summary>

See .planning/milestones/v1.0-ROADMAP.md for v1.0 details. 7 phases, 17 plans, 30 requirements delivered.

</details>

<details>
<summary>v2.0 Post-Processing + Robustness (Phases 8-10) - SHIPPED 2026-02-02</summary>

See .planning/milestones/v2.0-ROADMAP.md for v2.0 details. 3 phases, 8 plans, 20 requirements delivered.

</details>

### v2.1 Performance (In Progress)

**Milestone Goal:** Optimize Surya OCR performance on Apple Silicon through MPS acceleration, model caching, and cross-file batching. Expected cumulative improvement: 5-15x for multi-file batches.

- [ ] **Phase 11: Benchmarking Foundation & Metrics Fixes** - Establish baseline measurements, fix timing/metadata bugs
- [ ] **Phase 12: Device Configuration** - MPS device selection and validation
- [ ] **Phase 13: Model Caching** - Persist loaded models across MCP requests
- [ ] **Phase 14: Cross-File Batching** - Aggregate flagged pages across all files

## Phase Details

### Phase 11: Benchmarking Foundation & Metrics Fixes
**Goal**: Establish baseline performance measurements and fix timing/metadata bugs that would invalidate benchmarks.
**Depends on**: Nothing (first phase of v2.1)
**Requirements**: BENCH-01, BENCH-02, BENCH-03, BENCH-04, BENCH-05, BENCH-06, BENCH-07, BENCH-08
**Success Criteria** (what must be TRUE):
  1. Running `pytest --benchmark-only` produces statistical performance data for model loading and OCR processing
  2. Benchmark results include proper GPU synchronization (torch.mps.synchronize) for accurate MPS timing
  3. Memory profiling with memray generates flame graphs showing allocation patterns
  4. CI pipeline fails if performance regresses beyond threshold
  5. Hardware-specific profiles (M1/M2/M3) can be selected for appropriate baselines
  6. Surya model load time and inference time appear in phase_timings
  7. Top-level engine field is "mixed" when some pages used Surya, "surya" when all did
  8. Quality scores are re-evaluated after Surya processing (both scores preserved if fallback occurred)
**Plans**: 5 plans

Plans:
- [ ] 11-01-PLAN.md — Benchmark infrastructure (dependencies, timing module, fixtures)
- [ ] 11-02-PLAN.md — Benchmark tests (model loading, inference, memory)
- [ ] 11-03-PLAN.md — OCREngine.MIXED enum and compute_engine_from_pages
- [ ] 11-04-PLAN.md — Pipeline fixes (Surya timing, engine field, quality re-eval)
- [ ] 11-05-PLAN.md — CI workflow for regression detection

### Phase 12: Device Configuration
**Goal**: Enable explicit MPS device selection with validation and fallback for Apple Silicon GPU acceleration.
**Depends on**: Phase 11 (need benchmarks to validate improvements)
**Requirements**: DEV-01, DEV-02, DEV-03, DEV-04
**Success Criteria** (what must be TRUE):
  1. Pipeline explicitly uses MPS device on Apple Silicon (visible in logs: "Using device: mps")
  2. Startup validates MPS availability and shows actionable error if unavailable
  3. Processing automatically falls back to CPU when MPS fails mid-job
  4. Detection model runs on CPU while recognition runs on MPS (workaround for MPS bugs)
**Plans**: TBD

Plans:
- [ ] 12-01: TBD

### Phase 13: Model Caching
**Goal**: Eliminate repeated model loading overhead for MCP server by persisting loaded Surya models across requests.
**Depends on**: Phase 12 (need device configuration for correct model loading)
**Requirements**: MODEL-01, MODEL-02, MODEL-03, MODEL-04, MODEL-05
**Success Criteria** (what must be TRUE):
  1. Second MCP OCR request processes without 30-60s model loading delay
  2. Cached models evict automatically after configurable TTL (default 30 minutes)
  3. Memory cleanup between documents prevents accumulation (empty_cache + gc.collect)
  4. MCP server startup can pre-load models when configured (warm pool)
  5. Memory profiling shows VRAM usage during processing (accessible via API or logs)
**Plans**: TBD

Plans:
- [ ] 13-01: TBD

### Phase 14: Cross-File Batching
**Goal**: Process all flagged pages across multiple files in a single Surya batch, maximizing GPU utilization.
**Depends on**: Phase 13 (need model caching for efficient batch processing)
**Requirements**: BATCH-01, BATCH-02, BATCH-03, BATCH-04, BATCH-05
**Success Criteria** (what must be TRUE):
  1. Processing 5 files with 10 flagged pages each produces one Surya batch of 50 pages (not 5 batches)
  2. Batch size is configurable via environment variables (RECOGNITION_BATCH_SIZE, DETECTOR_BATCH_SIZE)
  3. Default batch sizes adjust based on available memory (smaller on 8GB, larger on 32GB+)
  4. Surya results map back correctly to source files (per-file, per-page)
  5. Batch size adapts if memory pressure detected during processing
**Plans**: TBD

Plans:
- [ ] 14-01: TBD

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-7 | v1.0 | 17/17 | Complete | 2026-02-02 |
| 8-10 | v2.0 | 8/8 | Complete | 2026-02-02 |
| 11. Benchmarking Foundation | v2.1 | 0/5 | Planned | - |
| 12. Device Configuration | v2.1 | 0/? | Not started | - |
| 13. Model Caching | v2.1 | 0/? | Not started | - |
| 14. Cross-File Batching | v2.1 | 0/? | Not started | - |
