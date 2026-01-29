# Phase 3: OCR Backend Modules - Context

**Gathered:** 2026-01-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Extract Tesseract and Surya OCR operations from the monolithic `PDFProcessor` into focused, testable backend modules (`tesseract.py`, `surya.py`) with proper model lifecycle management. This is an internal architecture phase — no user-facing behavior changes.

</domain>

<decisions>
## Implementation Decisions

### Module boundaries
- Claude's discretion: common protocol vs independent module shapes
- Claude's discretion: file-level I/O vs in-memory data boundaries (based on ocrmypdf/Marker API fit)
- Claude's discretion: PDF manipulation utilities placement (processor, shared module, or backends)
- Claude's discretion: batch processing scope (surya module vs orchestrator, respecting Phase 3/4 boundary)
- Claude's discretion: processor.py fate after extraction (thin shell vs removal)
- Claude's discretion: functions vs classes per backend
- Claude's discretion: lazy import strategy for torch/marker

### Error semantics
- Claude's discretion: exceptions vs result objects for failure reporting (leverage Phase 1 exception hierarchy)
- Claude's discretion: error granularity — whether backends distinguish quality vs crash failures
- Claude's discretion: Surya model load failure handling (fatal vs graceful degradation)
- Claude's discretion: logging ownership (backends vs orchestrator)
- Claude's discretion: stderr capture detail level for subprocess errors
- Timeouts: configurable with adaptive defaults per operation type (Tesseract per-file, Surya model load, Surya batch). Sensible defaults that vary by operation, overridable via config
- Claude's discretion: partial batch failure handling
- Claude's discretion: input validation strategy
- Claude's discretion: temp file cleanup ownership

### Surya model lifecycle
- Claude's discretion: eager vs lazy model loading timing
- Claude's discretion: explicit cleanup (context manager/close) vs GC
- Claude's discretion: GPU requirement vs CPU fallback
- Claude's discretion: fixed vs memory-aware batch sizing
- Claude's discretion: whether to accept externally pre-loaded models
- Claude's discretion: progress reporting from backend vs orchestrator
- Claude's discretion: Marker version pinning strategy

### Backend testability
- Both unit tests (mocked) AND integration tests (real Tesseract/Surya) required
- Claude's discretion: test gating mechanism (pytest marks vs separate directories)
- Test fixtures: minimal generated PDFs for unit tests, plus a user-provided real scanned PDF for integration tests
- Claude's discretion: dependency checking functions (is_available/check_dependencies)
- Claude's discretion: edge case coverage scope (proportionate to Phase 3)
- Claude's discretion: lazy import verification tests

### Claude's Discretion
Most module boundary and error handling decisions are at Claude's discretion — the user trusts Claude to make choices that fit the existing codebase patterns, the Phase 1 foundation, and the actual APIs of ocrmypdf/Marker/Surya. The two firm decisions are:

1. **Timeouts must be configurable** with adaptive defaults per operation type
2. **Both unit and integration tests** are required, with real PDF fixtures provided by the user

</decisions>

<specifics>
## Specific Ideas

- Timeouts should have different defaults depending on the operation — Tesseract per-file processing, Surya model loading, and Surya batch processing are different beasts with different reasonable timeouts
- User will provide a real scanned academic PDF for integration test fixtures
- Generated minimal PDFs (known text content) for unit test fixtures

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-ocr-backend-modules*
*Context gathered: 2026-01-29*
