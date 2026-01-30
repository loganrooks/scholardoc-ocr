# Phase 5: CLI Presentation Layer - Context

**Gathered:** 2026-01-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Thin CLI wrapper around the library API that preserves the existing `ocr` command interface while enabling programmatic use. The CLI handles argument parsing, Rich progress display, and result formatting — no direct access to backend modules. Existing flags must work identically.

</domain>

<decisions>
## Implementation Decisions

### Progress display
- Rich progress bars (animated, with file names, percentage)
- Explicit "Loading Surya models..." message with spinner when Surya initializes (users need to know why it pauses)
- Rich is the progress library of choice

### Color output
- Color enabled by default (green success, yellow warnings, red errors)
- Auto-detect terminal support

### New flags
- `--output-dir` / `-o` — Specify output directory for OCR'd files (instead of in-place); auto-create directory if it doesn't exist (mkdir -p behavior)
- `--language` / `-l` — Override default language list; CLI maps internally to both Tesseract and Surya codes
- `-r` short flag for `--recursive`
- All existing flags preserved as-is: positional path, `--quality`, `--force`, `--recursive`, `-w`, `--force-surya`

### Recursive mode fix
- Known bug in recursive mode file path handling — Claude to investigate and fix during implementation

### Claude's Discretion
- Quiet mode (--quiet flag or not)
- Overall ETA vs per-file-only progress
- Separate Surya progress display vs unified flow
- Rich as required vs optional dependency (with fallback)
- Progress detail level per file
- Final summary format (Rich table vs compact lines)
- Per-page quality scores in normal output vs verbose-only
- Color disable mechanism (--no-color flag and/or NO_COLOR env var)
- Exit code strategy for partial failures
- Error presentation style (continue-all vs stop-on-first)
- Helpful hints in error messages
- Traceback visibility (clean message default with --debug, or always)
- stderr vs stdout separation
- No-PDFs-found behavior
- --dry-run flag
- Permission error handling (skip vs abort)
- --version flag
- --language format (ISO codes vs Tesseract format)

</decisions>

<specifics>
## Specific Ideas

- Short flags for common options: `-o` (output-dir), `-l` (language), `-r` (recursive), `-w` (workers)
- User wants the simplified flag experience — easy to type common operations

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-cli-presentation-layer*
*Context gathered: 2026-01-29*
