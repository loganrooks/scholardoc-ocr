# Roadmap: scholardoc-ocr

## Overview

This roadmap rebuilds the scholardoc-ocr hybrid OCR pipeline from the ground up to fix critical architectural problems while preserving its core two-phase strategy (Tesseract-first, Surya fallback). The rebuild follows a bottom-up dependency order: establish clean data structures and contracts, enhance quality analysis with multi-signal scoring, extract OCR backends into testable modules, fix engine orchestration with per-file batching, and finally wrap everything in a thin CLI presentation layer. The result is a working pipeline with both CLI and library API, comprehensive test coverage, and the two critical Surya bugs fixed.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation and Data Structures** - Clean API contracts, context managers, exception hierarchy
- [x] **Phase 2: Quality Analysis Enhancement** - Multi-signal scoring with confidence, dictionary, German support
- [x] **Phase 3: OCR Backend Modules** - Extract Tesseract/Surya wrappers, fix model lifecycle
- [ ] **Phase 4: Engine Orchestration** - Per-file batching, fix Surya writeback, resource-aware parallelism
- [ ] **Phase 5: CLI Presentation Layer** - Thin CLI wrapper around library API, preserve interface

## Phase Details

### Phase 1: Foundation and Data Structures
**Goal**: Establish clean library API contracts and resource-safe PDF operations that all other phases build on.

**Depends on**: Nothing (first phase)

**Requirements**: API-01, API-02, API-03, API-04, ARCH-03, CLEAN-01, CLEAN-02, TEST-02

**Success Criteria** (what must be TRUE):
  1. Library code can be called programmatically without CLI (no sys.exit, no Rich imports)
  2. All PDF operations use context managers (no file handle leaks)
  3. Pipeline returns structured results (per-file, per-page quality scores and status)
  4. Progress reporting works via callback protocol (decoupled from Rich)
  5. Dead code removed and invalid type annotations fixed

**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md — Create leaf modules: types.py, callbacks.py, exceptions.py
- [x] 01-02-PLAN.md — Clean up existing code: context managers, Rich removal, dead code
- [x] 01-03-PLAN.md — Wire public API and create unit tests
- [x] 01-04-PLAN.md — Wire callbacks into pipeline and processor (gap closure)

### Phase 2: Quality Analysis Enhancement
**Goal**: Replace regex-only quality detection with multi-signal composite scoring using OCR confidence, dictionary validation, and extended language support.

**Depends on**: Phase 1 (uses data structures, PDF context managers)

**Requirements**: QUAL-01, QUAL-02, QUAL-03, LANG-01, LANG-02, TEST-01

**Success Criteria** (what must be TRUE):
  1. Quality scoring integrates Tesseract word-level confidence from hOCR output
  2. Composite quality score combines confidence, dictionary hits, garbled regex, and layout checks
  3. Per-page quality breakdown available in pipeline results
  4. German language support added (Tesseract: deu, Surya: de)
  5. Academic term whitelists include German philosophical vocabulary
  6. Quality analysis has comprehensive unit tests covering scoring edge cases

**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Dictionary signal module, bundled word list, German vocabulary
- [x] 02-02-PLAN.md — Tesseract confidence extraction module (pytesseract)
- [x] 02-03-PLAN.md — Composite quality analyzer refactor and unit tests

### Phase 3: OCR Backend Modules
**Goal**: Extract Tesseract and Surya OCR operations from monolithic processor into focused, testable backend modules with proper model lifecycle management.

**Depends on**: Phase 1 (uses PDF context managers, data structures)

**Requirements**: ARCH-05, TEST-02

**Success Criteria** (what must be TRUE):
  1. Tesseract wrapper (tesseract.py) isolates ocrmypdf subprocess calls with clean error handling
  2. Surya wrapper (surya.py) handles lazy model loading and per-file batch processing
  3. Surya models load once per pipeline run and share across files in main process
  4. Backend modules can be tested independently without running full pipeline
  5. ML model imports lazy-load (torch/marker not imported at module level)

**Plans**: 3 plans

Plans:
- [x] 03-01-PLAN.md — Tesseract backend module with ocrmypdf Python API and unit tests
- [x] 03-02-PLAN.md — Surya backend module with model lifecycle and unit tests
- [x] 03-03-PLAN.md — Processor cleanup and package export wiring

### Phase 4: Engine Orchestration
**Goal**: Fix pipeline orchestration to use per-file Surya batching with shared models, eliminate cross-file index mapping, and write Surya results back to output files.

**Depends on**: Phase 2 (uses enhanced quality analysis), Phase 3 (uses backend modules)

**Requirements**: BUG-01, BUG-02, ARCH-01, ARCH-02, ARCH-04, TEST-03, TEST-04

**Success Criteria** (what must be TRUE):
  1. Surya OCR results written back to output files (writeback bug fixed)
  2. Surya batch output correctly extracted from rendered markdown (extraction bug fixed)
  3. Per-file Surya batching eliminates fragile cross-file page index mapping
  4. Resource-aware parallelism coordinates CPU usage (pool workers with ocrmypdf jobs)
  5. Integration test verifies Surya text actually appears in final output file
  6. Pipeline orchestration separated from UI presentation (library vs CLI concerns)

**Plans**: 3 plans

Plans:
- [ ] 04-01-PLAN.md — Rewrite pipeline.py with per-file Surya batching, writeback, and resource-aware parallelism
- [ ] 04-02-PLAN.md — Update CLI with --force-surya flag and BatchResult formatting, export pipeline API
- [ ] 04-03-PLAN.md — Pipeline integration tests (writeback verification, partial failure, force_surya)

### Phase 5: CLI Presentation Layer
**Goal**: Create thin CLI wrapper around library API that preserves existing interface while enabling programmatic use.

**Depends on**: Phase 4 (wraps engine API)

**Requirements**: CLI-01, CLI-02, CLI-03

**Success Criteria** (what must be TRUE):
  1. CLI wraps library API exclusively (no direct access to backend modules)
  2. Existing CLI interface preserved (ocr command, current flags work identically)
  3. Recursive mode file path handling fixed
  4. Rich progress callbacks implemented as one option for progress reporting
  5. CLI can be completely rewritten without touching library code

**Plans**: TBD

Plans:
- [ ] 05-01: [To be determined during planning]

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and Data Structures | 4/4 | Complete ✓ | 2026-01-29 |
| 2. Quality Analysis Enhancement | 3/3 | Complete ✓ | 2026-01-29 |
| 3. OCR Backend Modules | 3/3 | Complete ✓ | 2026-01-29 |
| 4. Engine Orchestration | 0/? | Not started | - |
| 5. CLI Presentation Layer | 0/? | Not started | - |
