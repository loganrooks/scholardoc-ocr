# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

scholardoc-ocr is a hybrid OCR pipeline for academic texts. It uses a two-phase strategy: fast Tesseract OCR first, then Surya/Marker OCR only on pages that fall below a quality threshold. This minimizes expensive GPU model loads.

## Commands

```bash
# Install in development mode
pip install -e ".[dev]"

# Install with MCP server support
pip install -e ".[mcp]"

# Run OCR on a PDF or directory
ocr ~/Documents/scans
ocr --quality 0.9 --force --recursive -w 8 ~/scans

# Run MCP server (for Claude Desktop integration)
scholardoc-ocr-mcp

# Lint
ruff check src/
ruff format --check src/

# Run all tests
pytest

# Run a single test file
pytest tests/test_pipeline.py -v

# Run a single test
pytest tests/test_quality.py::TestQualityAnalyzer::test_analyze_pages -v

# Run MCP server tests
pytest tests/test_mcp_server.py -v

# Run benchmarks
pytest tests/benchmarks/ -v
```

## Architecture

### Core Pipeline Flow

```
CLI → PipelineConfig → run_pipeline() → BatchResult
                            │
        ┌───────────────────┴───────────────────┐
        ▼                                       ▼
   Phase 1: Tesseract                    Phase 2: Surya
   (ProcessPoolExecutor)                 (cross-file batch)
        │                                       │
        ▼                                       ▼
   QualityAnalyzer                      ModelCache.get_models()
   flags low-quality pages              loads once, shared across files
```

### Module Organization (`src/scholardoc_ocr/`)

**Entry Points**
- `cli.py` — CLI argument parsing, constructs `PipelineConfig`
- `mcp_server.py` — FastMCP server exposing `ocr`, `ocr_async`, `ocr_status`, `ocr_memory_stats` tools

**Pipeline Orchestration**
- `pipeline.py` — `run_pipeline()` two-phase orchestration, parallel Tesseract workers, batched Surya
- `batch.py` — Cross-file batch processing: `collect_flagged_pages()`, `split_into_batches()`, `map_results_to_files()`

**OCR Engines**
- `tesseract.py` — Tesseract wrapper via ocrmypdf
- `surya.py` — Surya/Marker wrapper with CPU fallback
- `model_cache.py` — Singleton `ModelCache` with TTL for Surya models, GPU memory management

**Quality Analysis**
- `quality.py` — `QualityAnalyzer` with regex garbled-text detection, page-level scoring
- `confidence.py` — Confidence scoring utilities
- `dictionary.py` — Academic term whitelist (philosophy, Greek transliterations)

**Infrastructure**
- `types.py` — `OCREngine`, `PageResult`, `FileResult`, `BatchResult` dataclasses
- `callbacks.py` — `PipelineCallback` protocol, `ProgressEvent`, `PhaseEvent`, `ModelEvent`
- `processor.py` — `PDFProcessor` wrapping PyMuPDF for page extraction/replacement
- `postprocess.py` — Text cleanup (dehyphenation, paragraph joining)
- `device.py` — Hardware detection (MPS/CUDA/CPU)
- `environment.py` — Environment validation
- `exceptions.py` — Custom exceptions
- `logging_.py` — Queue-based logging for multiprocessing
- `timing.py` — Performance timing utilities

### Key Patterns

**ModelCache Singleton**: Surya models are expensive to load (~3-5s). `ModelCache.get_instance()` ensures one load per process with configurable TTL eviction.

**Cross-file Batching**: Phase 2 collects all flagged pages across all files into a single batch for Surya, minimizing model load overhead. Memory pressure triggers sub-batch splitting.

**Callback System**: `PipelineCallback` protocol enables progress reporting. MCP server uses `_JobProgressCallback` to update async job state.

## Key Design Decisions

- Quality threshold (default 0.85) controls Tesseract-vs-Surya tradeoff per page
- Language support: English, French, Greek, Latin, German
- Phase 2 batches flagged pages across files to amortize model load cost
- MCP server supports both sync (`ocr`) and async (`ocr_async` + `ocr_status`) operations

## MCP Server Configuration

For Claude Desktop, add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "scholardoc-ocr": {
      "command": "/path/to/.venv/bin/python",
      "args": ["-m", "scholardoc_ocr.mcp_server"],
      "env": {
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
      }
    }
  }
}
```

## Python and Tooling

- Python >=3.11, <3.14
- Build system: hatchling
- Linter: ruff (line-length 100, rules: E, F, I, N, W)
- Package source layout: `src/scholardoc_ocr/`
