# scholardoc-ocr

## What This Is

A hybrid OCR pipeline for academic texts that uses fast Tesseract OCR first, then falls back to Surya/Marker neural OCR only on pages that fail multi-signal quality analysis. Designed for humanities scholars processing scanned philosophical, theological, historical, and classical texts in multiple languages (English, French, German, Greek, Latin). Usable as a CLI tool, Python library, or MCP tool for Claude Desktop.

## Core Value

Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.

## Requirements

### Validated

- ✓ Fix Surya writeback bug (results discarded) — v1.0
- ✓ Fix Surya output extraction bug (re-read original text) — v1.0
- ✓ Clean Python library API callable without CLI — v1.0
- ✓ Structured results (per-file, per-page quality scores) — v1.0
- ✓ Progress reporting via callback protocol — v1.0
- ✓ No sys.exit() in library; proper exceptions — v1.0
- ✓ Pipeline/UI separation — v1.0
- ✓ Per-file Surya batching with shared model — v1.0
- ✓ Resource-safe PDF handling (context managers) — v1.0
- ✓ CPU coordination (workers × jobs ≤ cores) — v1.0
- ✓ Surya models loaded once, shared across files — v1.0
- ✓ Multi-signal quality scoring (confidence + garbled + dictionary) — v1.0
- ✓ Per-page quality breakdown in results — v1.0
- ✓ German language support — v1.0
- ✓ German philosophical vocabulary whitelists — v1.0
- ✓ Thin CLI wrapping library API — v1.0
- ✓ Existing CLI interface preserved — v1.0
- ✓ Recursive file path handling fixed — v1.0
- ✓ MCP server for Claude Desktop — v1.0
- ✓ MCP extract_text, page_range, output_name parameters — v1.0
- ✓ Dead code removed, type annotations fixed — v1.0
- ✓ Comprehensive test suite (quality, backends, pipeline, integration) — v1.0

- ✓ Dehyphenation with language-aware edge cases (German compounds, French names) — v2.0
- ✓ Line break normalization (paragraph detection) — v2.0
- ✓ Unicode normalization (NFC, ligatures, soft hyphens) — v2.0
- ✓ Punctuation normalization — v2.0
- ✓ `--extract-text` flag triggering post-processing pipeline — v2.0
- ✓ RAG-ready .txt output alongside searchable PDF — v2.0
- ✓ Structured multiprocess logging (QueueHandler/QueueListener) — v2.0
- ✓ Full traceback capture in all error paths — v2.0
- ✓ Environment validation on startup (tesseract, langs, TMPDIR) — v2.0
- ✓ Work directory cleanup (`--keep-intermediates` to override) — v2.0
- ✓ Worker timeout protection — v2.0
- ✓ Per-worker log files with PID prefix — v2.0
- ✓ Startup diagnostic report — v2.0
- ✓ JSON metadata sidecar files — v2.0
- ✓ `--json` CLI flag for structured stdout output — v2.0
- ✓ MCP async job handling (ocr_async/ocr_status) — v2.0
- ✓ MCP progress events — v2.0

### Active

(No active requirements — define with `/gsd:new-milestone`)

### Out of Scope

- Surya-only mode — Tesseract-first is core value; two-phase approach is the differentiator
- GUI or web interface — CLI + library API + MCP sufficient for target users
- Non-PDF input formats — PDFs are the standard for scanned academic texts
- Cloud deployment or API server — local tool for individual scholars
- OCR training or model fine-tuning — use Tesseract and Surya as-is
- Click migration for CLI — argparse works; migration adds risk for marginal benefit
- Config file support (.scholardoc-ocr.yaml) — defer to v3.0; CLI flags sufficient for now
- Dictionary-based spell correction — defer to v3.0; high effort, medium impact
- Image preprocessing (cv2) — defer to v3.0; adds heavy dependency for uncertain gain
- Per-region quality scoring — defer to v3.0; complex, benefits fewer documents

## Context

Shipped v2.0 with 4,860 LOC Python (3,078 library + 1,782 tests).
Tech stack: ocrmypdf, PyMuPDF, marker-pdf, pytesseract, Rich, FastMCP.
Build: hatchling. Lint: ruff. Python >=3.11, <3.14.

Layered architecture:
- types.py, callbacks.py, exceptions.py (foundation)
- quality.py, dictionary.py, confidence.py (quality analysis)
- tesseract.py, surya.py, processor.py (backends)
- postprocess.py (text transforms)
- logging_.py, environment.py (robustness)
- pipeline.py (orchestration)
- cli.py (presentation)
- mcp_server.py (MCP integration)

v3.0 candidates: dictionary-based spell correction, config file support, image preprocessing, per-region quality scoring, n-gram perplexity scoring, layout consistency checks, configurable domain dictionaries.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Rearchitect rather than patch | Critical bugs + architectural issues compound | ✓ Good — clean foundation |
| Per-file Surya batching over monolithic combined PDF | Index mapping in combined PDF is brittle | ✓ Good — partial failure recovery |
| Library + CLI design | Enables programmatic use, testability, separation of concerns | ✓ Good — MCP server built on library |
| Include tests in this milestone | No existing tests; rearchitecture is the right time | ✓ Good — 79+ tests |
| Multi-signal quality analysis | Regex-only missed structural/layout errors | ✓ Good — composite scoring |
| Function module pattern for OCR backends | Simpler than classes for stateless operations | ✓ Good |
| Lazy Surya imports | Avoid loading torch/ML models at startup | ✓ Good — fast CLI/MCP startup |
| Composite weights 0.4/0.3/0.3 | Garbled regex most reliable signal | — Pending real-world validation |
| QueueHandler/QueueListener for logging | fork+logging broken on macOS | ✓ Good — workers log reliably |
| dehyphenate before join_paragraphs | Hyphen-newline pattern needs raw newlines | ✓ Good |
| Pipeline .txt files for MCP extract_text | Re-extraction loses post-processing | ✓ Good — preserves transforms |

## Constraints

- **Python**: >=3.11, <3.14
- **Dependencies**: ocrmypdf, pymupdf, marker-pdf, rich, fastmcp
- **Build**: hatchling
- **Lint**: ruff, line-length 100, rules E/F/I/N/W
- **Backwards compatibility**: CLI interface (`ocr` command) must remain stable
- **Tesseract-first**: Two-phase architecture is core value

---
*Last updated: 2026-02-03 after v2.0 milestone*
