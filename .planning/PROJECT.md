# scholardoc-ocr

## What This Is

A hybrid OCR pipeline for academic texts that uses fast Tesseract OCR first, then falls back to Surya/Marker neural OCR only on pages that fail multi-signal quality analysis. Optimized for Apple Silicon with MPS GPU acceleration, model caching, and cross-file batching. Designed for humanities scholars processing scanned philosophical, theological, historical, and classical texts in multiple languages (English, French, German, Greek, Latin). Usable as a CLI tool, Python library, or MCP tool for Claude Desktop.

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

- ✓ Explicit MPS device selection for Apple Silicon GPU acceleration — v2.1
- ✓ Cross-file page batching (collect flagged pages across files, process as one batch) — v2.1
- ✓ Improved Surya parallelization and resource utilization — v2.1
- ✓ Memory optimization to reduce peak usage during Surya processing — v2.1
- ✓ Model caching to persist loaded models across MCP calls — v2.1
- ✓ Benchmarking infrastructure to measure and validate improvements — v2.1

### Active

**v3.0 Diagnostic Intelligence** — Understand where and why OCR fails before building fixes.

- Diagnostic enrichment (image quality metrics, layout detection, char-level confidence, signal disagreement, Surya diffs, post-processing delta)
- Struggle taxonomy (categorize failure modes beyond composite score)
- Test corpus of difficult philosophy PDFs (Simondon, Derrida) with smart page selection
- LLM evaluation framework (versioned templates, CLI-based Claude/Codex evaluation, structured output)
- Quality scoring calibration against ground truth (threshold, weights, signal floors)
- Targeted improvements driven by diagnostic findings

### Out of Scope

- Surya-only mode — Tesseract-first is core value; two-phase approach is the differentiator
- GUI or web interface — CLI + library API + MCP sufficient for target users
- Non-PDF input formats — PDFs are the standard for scanned academic texts
- Cloud deployment or API server — local tool for individual scholars
- OCR training or model fine-tuning — use Tesseract and Surya as-is
- Click migration for CLI — argparse works; migration adds risk for marginal benefit
- Config file support (.scholardoc-ocr.yaml) — defer to future; CLI flags sufficient for now
- Per-region quality scoring — defer to future; complex, benefits fewer documents
- Multi-GPU support — Single Apple Silicon GPU is target use case
- CUDA optimization — Apple Silicon only; CUDA supported but not optimized
- Distributed processing — Single-machine tool for individual scholars
- MLX migration — PyTorch MPS sufficient, MLX would be major rewrite
- torch.compile optimization — MPS support is experimental, not stable enough

## Context

Shipped v2.1 with 4,465 LOC Python library + ~2,500 LOC tests.
Tech stack: ocrmypdf, PyMuPDF, marker-pdf, pytesseract, Rich, FastMCP, cachetools.
Build: hatchling. Lint: ruff. Python >=3.11, <3.14.

Layered architecture:
- types.py, callbacks.py, exceptions.py (foundation)
- quality.py, dictionary.py, confidence.py (quality analysis)
- tesseract.py, surya.py, processor.py (backends)
- device.py, timing.py (hardware abstraction)
- model_cache.py, batch.py (performance)
- postprocess.py (text transforms)
- logging_.py, environment.py (robustness)
- pipeline.py (orchestration)
- cli.py (presentation)
- mcp_server.py (MCP integration)

Performance characteristics (v2.1):
- MPS GPU acceleration with automatic CUDA > MPS > CPU fallback
- Model caching eliminates 30-60s load time on subsequent requests
- Cross-file batching processes all flagged pages in single Surya call
- Adaptive batch sizing prevents OOM on memory-constrained systems
- Expected 5-15x improvement for multi-file batches

v3.0 focus: Diagnostic intelligence — instrument the pipeline to capture what we throw away (image quality, layout data, char-level confidence, signal disagreement, Surya comparison diffs), build an LLM evaluation framework to establish ground truth on real philosophy PDFs, calibrate quality scoring empirically, then apply targeted improvements based on data rather than speculation. New dependencies: Pillow/numpy for image analysis. Evaluation via claude CLI and codex CLI (account-based, not API).

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
| Benchmarking first (v2.1) | Establish baseline before optimization | ✓ Good — valid measurements |
| TTLCache maxsize=1 | Surya models too large for multiple cached sets | ✓ Good — single model cache |
| Cross-file batching | N files → 1 Surya call vs N calls | ✓ Good — 5-15x expected improvement |
| Adaptive batch sizing | Prevent OOM on 8GB machines | ✓ Good — memory-aware processing |
| Measure before you fix (v3.0) | Speculative features waste effort; data-driven improvements don't | — Pending |
| CLI-based LLM evaluation over API | Uses existing Claude/Codex accounts, no SDK dependency, repeatable via templates | — Pending |
| Independent evaluation framework | Keep separate from hermeneutic_mcp; reusable for any OCR output | — Pending |

## Constraints

- **Python**: >=3.11, <3.14
- **Dependencies**: ocrmypdf, pymupdf, marker-pdf, rich, fastmcp, cachetools
- **Build**: hatchling
- **Lint**: ruff, line-length 100, rules E/F/I/N/W
- **Backwards compatibility**: CLI interface (`ocr` command) must remain stable
- **Tesseract-first**: Two-phase architecture is core value

## Open Questions

| Question | Why It Matters | Criticality | Status |
|----------|----------------|-------------|--------|
| Are composite weights 0.4/0.3/0.3 correct? | Wrong weights = wrong pages flagged for Surya | Critical | Pending — Phase 4 calibration |
| Is 0.85 the right quality threshold? | Too high = unnecessary Surya; too low = bad text passes | Critical | Pending — Phase 4 calibration |
| What are the top failure modes on real philosophy PDFs? | Determines what Phase 5 improvements to build | Critical | Pending — Phase 4 analysis |
| Does Surya actually improve pages Tesseract flags? | If not, fallback strategy needs rethinking | Medium | Pending — Phase 1 comparison data |
| Which image preprocessing techniques help most? | Deskew, denoise, and contrast all have different costs and benefits | Medium | Pending — Phase 5 experimentation |

---
*Last updated: 2026-02-17 after v3.0 milestone start*
