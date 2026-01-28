# scholardoc-ocr

## What This Is

A hybrid OCR pipeline for academic texts that uses fast Tesseract OCR first, then falls back to Surya/Marker neural OCR only on pages that fail quality analysis. Designed for humanities scholars processing scanned philosophical, theological, historical, and classical texts in multiple languages (English, French, German, Greek, Latin). Usable both as a CLI tool and as a Python library.

## Core Value

Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.

## Requirements

### Validated

- Tesseract OCR integration via ocrmypdf subprocess -- existing
- PDF manipulation (page extraction, text extraction, page combination) via PyMuPDF -- existing
- CLI with argument parsing for input/output dirs, quality threshold, workers, debug mode -- existing
- Regex-based quality analysis with academic term whitelists (German philosophy, French, Greek transliterations) -- existing
- Parallel Tesseract processing via ProcessPoolExecutor -- existing
- Page-level quality analysis (individual page scoring, bad page identification) -- existing
- Rich terminal UI with progress indicators -- existing

### Active

- [ ] Fix Phase 2 Surya writeback (results currently discarded, never written to output)
- [ ] Fix Surya batch output extraction (currently re-reads original bad text instead of Surya output)
- [ ] Separate pipeline orchestration from UI presentation
- [ ] Clean Python library API that CLI wraps
- [ ] Per-file Surya batching with shared model (replace fragile monolithic combined PDF approach)
- [ ] Resource-safe PDF handling (context managers for all fitz operations)
- [ ] Improved quality analysis (structural checks beyond regex garbled detection)
- [ ] Proper file path handling (pass resolved paths, fix recursive mode)
- [ ] Coordinate CPU usage (pool workers x jobs_per_file <= total cores)
- [ ] Test coverage for quality analysis, processor, pipeline orchestration, and CLI
- [ ] Remove dead code (run_surya_on_pages) and stale references (LEVINAS, levinas_ocr defaults)

### Out of Scope

- Surya-only mode (dropping Tesseract-first) -- Tesseract is much faster and often sufficient; two-phase approach is the core value proposition
- GUI or web interface -- CLI + library API is sufficient
- Non-PDF input formats -- PDFs are the standard for scanned academic texts
- Cloud deployment or API server -- local tool for individual scholars
- OCR training or model fine-tuning -- use Tesseract and Surya as-is

## Context

The codebase has 4 modules (~1200 lines) with a working Phase 1 (parallel Tesseract) but a broken Phase 2 (Surya fallback). Two critical bugs mean Surya output is never actually used: the batch processor discards Surya's rendered output, and the pipeline never writes results back to files. Additionally, the pipeline module conflates orchestration, worker logic, and UI rendering in a single 600-line file, making it hard to test or use programmatically.

Primary use case: processing scanned Continental philosophy texts (Heidegger, Levinas, Derrida) and related humanities scholarship with heavy multilingual content -- German philosophical terms, French, Greek transliterations, Latin citations.

A CODE_REVIEW.md exists in the repo with detailed bug analysis. All findings verified accurate.

## Constraints

- **Python**: >=3.11, <3.14 (existing requirement)
- **Dependencies**: ocrmypdf, pymupdf, marker-pdf, rich (keep current stack)
- **Build**: hatchling (existing)
- **Lint**: ruff, line-length 100, rules E/F/I/N/W (existing)
- **Backwards compatibility**: CLI interface (`ocr` command) should remain the same
- **Tesseract-first**: Keep two-phase architecture. Tesseract runs first; Surya only on pages that fail quality.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Rearchitect rather than patch | Critical bugs + architectural issues compound; patching would leave fragile foundation | -- Pending |
| Per-file Surya batching over monolithic combined PDF | Index mapping in combined PDF is brittle; per-file with shared model is safer and allows partial failure recovery | -- Pending |
| Library + CLI design | Enables programmatic use, testability, and separation of concerns | -- Pending |
| Include tests in this milestone | No existing tests; rearchitecture is the right time to add them | -- Pending |
| Improve quality analysis | Current regex approach misses structural/layout errors and systematic misrecognitions | -- Pending |

---
*Last updated: 2026-01-28 after initialization*
