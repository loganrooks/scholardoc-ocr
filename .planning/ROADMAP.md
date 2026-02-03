# Roadmap: scholardoc-ocr

## Milestones

- v1.0 MVP - Phases 1-7 (shipped 2026-02-02)
- v2.0 Post-Processing + Robustness - Phases 8-10 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-7) - SHIPPED 2026-02-02</summary>

See .planning/MILESTONES.md for v1.0 details. 7 phases, 17 plans, 30 requirements delivered.

</details>

### v2.0 Post-Processing + Robustness (In Progress)

**Milestone Goal:** Produce RAG-ready text output from academic PDFs with robust operational behavior, structured logging, and async MCP support.

- [x] **Phase 8: Robustness** - Structured logging, environment validation, work directory management, timeout protection
- [ ] **Phase 9: Post-Processing** - Unicode normalization, dehyphenation, line break and punctuation cleanup for RAG-ready text
- [ ] **Phase 10: Output and MCP** - JSON metadata, CLI text extraction, async MCP job handling

## Phase Details

### Phase 8: Robustness
**Goal**: Pipeline operates reliably with observable diagnostics -- worker logs reach the console, environment problems surface before processing starts, work directories clean up, and runaway files get timed out.
**Depends on**: Nothing (first v2.0 phase)
**Requirements**: ROBU-01, ROBU-02, ROBU-03, ROBU-04, ROBU-05, ROBU-06, ROBU-07, ROBU-08
**Success Criteria** (what must be TRUE):
  1. User sees log output from worker processes during parallel OCR runs on macOS
  2. User gets a clear error at startup when tesseract binary or required language packs are missing
  3. Work directory is automatically removed after successful processing; `--keep-intermediates` preserves it
  4. A corrupted or slow PDF times out instead of hanging the entire pipeline
  5. User can inspect per-worker log files after a parallel run to diagnose failures
**Plans:** 4 plans

Plans:
- [x] 08-01-PLAN.md — Multiprocess logging infrastructure (QueueHandler/QueueListener, per-worker log files)
- [x] 08-02-PLAN.md — Environment validation and startup diagnostics
- [x] 08-03-PLAN.md — Full traceback capture in all error paths
- [x] 08-04-PLAN.md — Pipeline integration (logging, cleanup, timeout, CLI flags)

### Phase 9: Post-Processing
**Goal**: OCR text output is RAG-ready -- paragraphs are joined, hyphens resolved, unicode unified, punctuation cleaned -- without destroying academic content like philosophical terms, author names, or Greek transliterations.
**Depends on**: Phase 8 (structured logging needed for debugging transforms in workers)
**Requirements**: POST-01, POST-02, POST-03, POST-04, POST-05, POST-06, POST-07
**Success Criteria** (what must be TRUE):
  1. Extracted text uses consistent Unicode NFC form with ligatures decomposed and soft hyphens removed
  2. Paragraphs are joined into continuous text while paragraph boundaries (double newlines, indentation changes) are preserved
  3. Words split across lines with hyphens are rejoined; German compounds ("Selbstbewusstsein") and French names ("Merleau-Ponty") keep their intentional hyphens
  4. Punctuation is normalized -- extra whitespace around punctuation collapsed, double spaces removed
**Plans**: TBD

Plans:
- [ ] 09-01: TBD
- [ ] 09-02: TBD

### Phase 10: Output and MCP
**Goal**: Pipeline results are available in structured formats for programmatic consumers -- JSON metadata alongside PDFs, text extraction via CLI flag, and async MCP handling for long-running jobs.
**Depends on**: Phase 9 (JSON metadata includes post-processing status; MCP wraps complete pipeline)
**Requirements**: OUTP-01, OUTP-02, OUTP-03, OUTP-04, OUTP-05
**Success Criteria** (what must be TRUE):
  1. A JSON file is written alongside each output PDF containing per-page quality scores, engine provenance, and processing stats
  2. `ocr --extract-text` produces a post-processed .txt file alongside the searchable PDF
  3. `ocr --json` outputs structured JSON results to stdout
  4. MCP `ocr_async()` returns a job ID immediately; `ocr_status(job_id)` reports progress and retrieves results when done
**Plans**: TBD

Plans:
- [ ] 10-01: TBD
- [ ] 10-02: TBD

## Progress

**Execution Order:** Phase 8 -> Phase 9 -> Phase 10

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 8. Robustness | v2.0 | 4/4 | ✓ Complete | 2026-02-02 |
| 9. Post-Processing | v2.0 | 0/TBD | Not started | - |
| 10. Output and MCP | v2.0 | 0/TBD | Not started | - |
