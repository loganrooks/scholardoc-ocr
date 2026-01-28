# Technology Stack

**Analysis Date:** 2026-01-28

## Languages

**Primary:**
- Python 3.11-3.13 - Core implementation language, specified in `pyproject.toml`

**Secondary:**
- None detected

## Runtime

**Environment:**
- Python (CPython)
- Platform-specific: Apple Silicon optimized per README

**Package Manager:**
- pip - Primary package manager
- Lockfile: Not detected (using pinned versions in `pyproject.toml`)

## Frameworks

**Core:**
- ocrmypdf 16.0.0+ - Tesseract OCR wrapper for PDF processing (subprocess-based)
- marker-pdf 1.0.0+ - Surya OCR integration for advanced text extraction
- PyMuPDF (fitz) 1.24.0+ - PDF manipulation (page extraction, text extraction, merging)
- rich 13.0.0+ - Terminal UI with tables, progress bars, live updates

**Testing:**
- pytest 8.0.0+ - Unit test framework
- No explicit test runner configuration detected

**Build/Dev:**
- hatchling - Build backend (PEP 517/518 compliant)
- ruff 0.4.0+ - Linting and formatting

## Key Dependencies

**Critical:**
- ocrmypdf - Executes Tesseract OCR via subprocess, configured with language packs (eng, fra, ell, lat)
- marker-pdf - Provides Surya neural OCR model inference (models cached after first load)
- pymupdf - Handles all PDF I/O without subprocess overhead (text extraction per-page, page combination, merging)

**Infrastructure:**
- rich - Rich terminal output for progress visualization in `pipeline.py`

## Configuration

**Environment:**
- No environment variables required for operation
- Quality threshold configurable via CLI flag `--quality` (default 0.85)
- Languages hardcoded: Tesseract: `eng,fra,ell,lat`; Surya: `en,fr,el,la`

**Build:**
- `pyproject.toml` - Full build and project configuration (line-length 100, ruff rules E/F/I/N/W)
- Entry point defined: `ocr` command maps to `scholardoc_ocr.cli:main`
- Package layout: source in `src/scholardoc_ocr/`

## Platform Requirements

**Development:**
- Python 3.11, 3.12, or 3.13
- Tesseract OCR binary (external system dependency)
- Tesseract language packs for English, French, Greek, Latin
- Apple Silicon recommended but not required

**Production:**
- Same as development
- Output written to `<input_dir>/ocr_output` by default or custom `--output` directory
- Temporary work files in `output_dir/work/`, cleaned intermediate files

## External System Dependencies

**Tesseract OCR:**
- Invoked via `subprocess` in `run_tesseract()` at `src/scholardoc_ocr/processor.py:141-182`
- Command: `python -m ocrmypdf` with language flag and document output type `pdfa`
- Timeout: 600 seconds per file
- Output suppression via `DEVNULL` to reduce logging noise

**Surya Models:**
- Lazy-loaded via `marker.converters.pdf.PdfConverter` and `marker.models.create_model_dict()`
- Models cached in memory after first call to avoid repeated loading
- Batch processing in `run_surya_batch()` to manage memory usage with 50-page default batches

---

*Stack analysis: 2026-01-28*
