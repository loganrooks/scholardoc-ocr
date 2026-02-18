---
phase: 16-test-corpus-ground-truth
plan: 01
subsystem: evaluation-corpus
tags: [corpus, manifest, ground-truth, infrastructure, diagnostic-coverage]
requires:
  - phase: 15-diagnostic-infrastructure
    provides: "Diagnostic sidecar JSON with struggle_categories, signal_disagreements, gray_zone flags"
provides:
  - "tests/corpus/ directory structure with pdfs/, ground_truth/, baselines/, images/ subdirectories"
  - "corpus.json manifest describing 4 philosophy documents with pipeline version pinning"
  - "Corpus-local .gitignore preventing PDFs and images from being committed"
  - "render_pages.py script for 300 DPI page rendering for Opus transcription"
  - "build_coverage_matrix.py script for diagnostic-driven page selection"
affects: [16-02-document-registration, 16-03-baseline-capture, 17-evaluation-framework, 18-cer-wer, 19-correlation]
tech-stack:
  added: []
  patterns: [coverage-based-page-selection, corpus-manifest-schema, diagnostic-consumption]
key-files:
  created:
    - tests/corpus/.gitignore
    - tests/corpus/corpus.json
    - tests/corpus/ground_truth/.gitkeep
    - tests/corpus/baselines/.gitkeep
    - scripts/corpus/render_pages.py
    - scripts/corpus/build_coverage_matrix.py
  modified: []
key-decisions:
  - "0-indexed page numbers throughout corpus, matching PageResult.page_number convention"
  - "Coverage-based page selection with two categories: difficult (struggle categories) and regression (clean pages)"
  - "Corpus-local .gitignore for clean separation from root .gitignore"
patterns-established:
  - "Corpus manifest schema: version-pinned JSON with observable metadata and null-until-populated fields"
  - "Coverage matrix analysis: diagnostic sidecar consumption for empirical page selection"
duration: 12min
completed: 2026-02-18
---

# Phase 16 Plan 01: Corpus Infrastructure Summary

**Corpus directory structure, manifest schema, and helper scripts for diagnostic-driven evaluation corpus**

## Performance
- **Duration:** 12 minutes
- **Tasks:** 2 completed
- **Files created:** 6

## Accomplishments
- Created `tests/corpus/` directory structure with `pdfs/`, `ground_truth/`, `baselines/`, `images/` subdirectories
- Created `corpus.json` manifest describing 4 philosophy documents (Simondon, 3x Derrida) with pipeline version pinning (scholardoc-ocr 0.2.0, Tesseract 5.5.2, Surya 0.17.1, etc.)
- Added corpus-local `.gitignore` that prevents PDFs, rendered images, and pipeline output PDFs from being committed while allowing diagnostic JSON, ground truth text, and pipeline metadata
- Created `render_pages.py` script for rendering PDF pages as 300 DPI PNGs for Opus vision transcription, with `--all-selected` flag for batch rendering
- Created `build_coverage_matrix.py` script that parses Phase 15 diagnostic sidecars to build coverage matrices of struggle categories, gray zone pages, and signal disagreement pages, then recommends page selections for ground truth creation

## Task Commits
1. **Task 1: Create corpus directory structure, .gitignore, and manifest** - `7c51661`
2. **Task 2: Create helper scripts for page rendering and coverage matrix analysis** - `6c84ac3`

## Files Created/Modified
- `tests/corpus/.gitignore` - Corpus-local gitignore rules for PDFs, images, pipeline artifacts
- `tests/corpus/corpus.json` - Manifest with 4 document entries, pipeline version pinning, null baseline fields
- `tests/corpus/ground_truth/.gitkeep` - Placeholder for tracked empty directory
- `tests/corpus/baselines/.gitkeep` - Placeholder for tracked empty directory
- `scripts/corpus/render_pages.py` - CLI tool for 300 DPI page rendering via PyMuPDF
- `scripts/corpus/build_coverage_matrix.py` - Coverage matrix analysis and page selection from diagnostic baselines

## Deviations from Plan

None - plan executed exactly as written.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Corpus infrastructure is ready for CORP-02 (document registration with PDF symlinks)
- Manifest schema supports the full phased workflow: document metadata -> baseline -> page selection -> ground truth
- Helper scripts are functional and ready for use once baselines are captured (CORP-04)
- `build_coverage_matrix.py` gracefully reports "no baselines found" until baseline runs are complete

## Self-Check: PASSED
- All 6 created files verified on disk
- Both task commits (7c51661, 6c84ac3) verified in git log
