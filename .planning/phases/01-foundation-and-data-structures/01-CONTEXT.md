# Phase 1: Foundation and Data Structures - Context

**Gathered:** 2026-01-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Establish clean library API contracts, resource-safe PDF handling, structured result types, progress callback protocol, and exception hierarchy. This phase defines the data structures and interfaces that all subsequent phases build on. No OCR logic changes, no quality analysis changes, no CLI changes beyond dead code removal.

</domain>

<decisions>
## Implementation Decisions

### Result Structure
- Both per-file summary and per-page detail levels available (drill-in model)
- Per-page results include: composite quality score + individual signal scores (confidence, garbled ratio, dictionary hits), which OCR engine produced the final text, and whether the page was flagged for Surya (even if Surya didn't run)
- Text content optional in results — excluded by default, available via flag or method call
- Results JSON-serializable — dataclasses with to_dict/to_json methods
- Per-phase timing tracked (wall-clock for Tesseract phase, quality analysis, Surya phase)
- Batch run includes top-level summary (total files, pass/fail counts, aggregate stats) alongside per-file results

### Progress Callbacks
- Page-level granularity — events for every page processed within every file
- Phase-aware — events include which pipeline phase is active (Tesseract, Quality Analysis, Surya)
- Per-worker events tagged with worker ID (enables multi-bar displays for parallel Tesseract)
- Include ETA — library tracks processing rate and provides estimated remaining time
- Model loading events emitted (Surya model download/init start and finish)
- Minimal Python logging by default when no callback provided (INFO level)
- Ship a built-in LoggingCallback alongside the Rich callback
- Preserve current Rich multi-panel layout style (separate progress bars, status panels), driven by callbacks
- Claude's Discretion: callback interface design (protocol class vs single callable), cancellation mechanism, real-time quality score delivery vs end-only

### Exception Design
- Configurable batch failure behavior: default continue (collect errors), fail-fast flag to abort on first error
- Separate exception classes for different error types (OCR errors, PDF errors, config errors)
- Claude's Discretion: missing dependency handling (fail at start vs fail when needed), error detail level (chained cause vs clean message), upfront config validation vs lazy

### Module Boundaries
- Expose scholardoc_ocr.__version__ programmatically
- Claude's Discretion: public API surface design (class vs function vs both), internal module visibility (public vs private), file creation timing (skeletons now vs refactor later), __init__.py re-export strategy

</decisions>

<specifics>
## Specific Ideas

- Per-worker progress tagging enables the current Rich multi-panel layout showing each Tesseract worker's progress independently
- Phase-aware events enable UI showing "Phase 1/3: Running Tesseract..." progression
- Flagged-pages tracking enables a future dry-run mode (show which pages would trigger Surya without running it)
- JSON-serializable results enable piping pipeline output to external tools or saving as processing reports

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation-and-data-structures*
*Context gathered: 2026-01-28*
