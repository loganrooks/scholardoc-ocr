# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

scholardoc-ocr is a hybrid OCR pipeline for academic texts. It uses a two-phase strategy: fast Tesseract OCR first, then Surya/Marker OCR only on pages that fall below a quality threshold. This avoids loading expensive Surya models unless needed.

## Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Run OCR on a directory
ocr ~/Documents/scans

# Run with options
ocr --quality 0.9 --force --recursive -w 8 ~/scans

# Lint
ruff check src/
ruff format --check src/

# Run tests
pytest
```

## Architecture

The pipeline has four modules in `src/scholardoc_ocr/`:

- **cli.py** — Argument parsing, constructs `PipelineConfig`, calls `run_pipeline()`
- **pipeline.py** — Two-phase orchestration:
  - Phase 1: Parallel Tesseract OCR via `ProcessPoolExecutor`, then page-level quality analysis
  - Phase 2: Batched Surya OCR on all flagged pages across all files (models loaded once), results mapped back to originals
- **processor.py** — `PDFProcessor` class wrapping ocrmypdf (Tesseract), Marker/Surya, and PyMuPDF for PDF manipulation (extract/replace pages, text extraction)
- **quality.py** — `QualityAnalyzer` with regex-based garbled text detection and a whitelist of valid academic terms (German/French philosophy, Greek transliterations)

**Data flow:** CLI → `PipelineConfig` → `run_pipeline()` → parallel `_process_single()` workers → `PDFProcessor` + `QualityAnalyzer` → `ExtendedResult`

## Key Design Decisions

- Quality threshold (default 0.85) controls the Tesseract-vs-Surya tradeoff per page
- Surya batch processing across files minimizes model load overhead
- Language support: English, French, Greek, Latin (Tesseract: `eng,fra,ell,lat`; Surya: `en,fr,el,la`)
- Quality analysis whitelists philosophical terms to avoid false positives on valid non-English words

## Python and Tooling

- Python >=3.11, <3.14
- Build system: hatchling
- Linter: ruff (line-length 100, rules: E, F, I, N, W)
- Package source layout: `src/scholardoc_ocr/`
