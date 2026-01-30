# Requirements: scholardoc-ocr

**Defined:** 2026-01-28
**Core Value:** Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Critical Bug Fixes

- [x] **BUG-01**: Surya OCR results written back to output files (currently discarded at pipeline.py:564-567)
- [x] **BUG-02**: Surya batch output correctly extracted from rendered markdown (currently re-reads original bad text at processor.py:309-312)

### Library API

- [x] **API-01**: Clean Python library API that can be called without CLI
- [x] **API-02**: Pipeline returns structured results (per-file, per-page quality scores and status)
- [x] **API-03**: Progress reporting via callback protocol (not coupled to Rich)
- [x] **API-04**: No sys.exit() in library code; proper exception hierarchy

### Architecture

- [x] **ARCH-01**: Pipeline orchestration separated from UI presentation
- [x] **ARCH-02**: Per-file Surya batching with shared model (replace cross-file combined PDF approach)
- [x] **ARCH-03**: Resource-safe PDF handling (context managers for all fitz operations)
- [x] **ARCH-04**: Coordinate CPU usage (pool workers × jobs_per_file ≤ total cores)
- [x] **ARCH-05**: Surya models loaded once per pipeline run, shared across files in main process

### Quality Analysis

- [x] **QUAL-01**: Tesseract confidence scores integrated into quality scoring (hOCR word-level confidence)
- [x] **QUAL-02**: Composite quality score (confidence + garbled regex + dictionary hits)
- [x] **QUAL-03**: Per-page quality breakdown available in results

### Language Support

- [x] **LANG-01**: German language support added (Tesseract: deu, Surya: de) — required for Continental philosophy
- [x] **LANG-02**: Academic term whitelists updated for German philosophical vocabulary

### CLI

- [x] **CLI-01**: CLI wraps library API (thin presentation layer)
- [x] **CLI-02**: Existing CLI interface (`ocr` command, current flags) preserved
- [x] **CLI-03**: Recursive mode file path handling fixed

### Code Cleanup

- [x] **CLEAN-01**: Dead code removed (run_surya_on_pages, stale LEVINAS references)
- [x] **CLEAN-02**: Invalid type annotations fixed (lowercase `callable`)

### Testing

- [x] **TEST-01**: Unit tests for quality analysis (scoring, whitelists, edge cases)
- [x] **TEST-02**: Unit tests for PDF processor operations (extract, combine, text extraction)
- [x] **TEST-03**: Integration tests for pipeline orchestration (Phase 1 → Phase 2 flow)
- [x] **TEST-04**: Test verifying Surya output actually appears in final output file

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Quality Analysis v2

- **QUAL2-01**: Dictionary-based validation via hunspell/enchant for real-word substitution detection
- **QUAL2-02**: N-gram perplexity scoring for language model-based quality assessment
- **QUAL2-03**: Layout consistency checks (line spacing, column detection anomalies)

### Features v2

- **FEAT2-01**: Configurable domain dictionaries (user-supplied term whitelists)
- **FEAT2-02**: JSON/structured output format option
- **FEAT2-03**: Dry-run mode showing which pages would trigger Surya without running it

## Out of Scope

| Feature | Reason |
|---------|--------|
| Surya-only mode | Tesseract-first is core value; two-phase approach is the differentiator |
| GUI or web interface | CLI + library API sufficient for target users (individual scholars) |
| Non-PDF input formats | PDFs are the standard for scanned academic texts |
| Cloud deployment / API server | Local tool for individual scholars |
| OCR training / model fine-tuning | Use Tesseract and Surya as-is |
| Click migration for CLI | argparse works; migration adds risk for marginal benefit in v1 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BUG-01 | Phase 4 | Complete |
| BUG-02 | Phase 4 | Complete |
| API-01 | Phase 1 | Complete |
| API-02 | Phase 1 | Complete |
| API-03 | Phase 1 | Complete |
| API-04 | Phase 1 | Complete |
| ARCH-01 | Phase 4 | Complete |
| ARCH-02 | Phase 4 | Complete |
| ARCH-03 | Phase 1 | Complete |
| ARCH-04 | Phase 4 | Complete |
| ARCH-05 | Phase 3 | Complete |
| QUAL-01 | Phase 2 | Complete |
| QUAL-02 | Phase 2 | Complete |
| QUAL-03 | Phase 2 | Complete |
| LANG-01 | Phase 2 | Complete |
| LANG-02 | Phase 2 | Complete |
| CLI-01 | Phase 5 | Pending |
| CLI-02 | Phase 5 | Pending |
| CLI-03 | Phase 5 | Pending |
| CLEAN-01 | Phase 1 | Complete |
| CLEAN-02 | Phase 1 | Complete |
| TEST-01 | Phase 2 | Complete |
| TEST-02 | Phase 1 | Complete |
| TEST-03 | Phase 4 | Complete |
| TEST-04 | Phase 4 | Complete |

**Coverage:**
- v1 requirements: 25 total
- Mapped to phases: 25
- Unmapped: 0

---
*Requirements defined: 2026-01-28*
*Last updated: 2026-01-28 after research synthesis*
