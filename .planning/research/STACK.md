# Technology Stack: v2.0 Additions

**Project:** scholardoc-ocr v2.0
**Researched:** 2026-02-02
**Scope:** Stack additions for post-processing, structured logging, MCP resilience, env validation

## Executive Summary

v2.0 needs zero new dependencies. Every feature maps to Python stdlib modules. This is the correct call -- adding libraries for simple text transforms or logging would be over-engineering.

## Feature-to-Stack Mapping

### 1. Text Post-Processing (dehyphenation, unicode, line breaks)

**Stack: Python stdlib only**

| Module | Purpose | Notes |
|--------|---------|-------|
| `unicodedata` (stdlib) | Unicode normalization (NFC/NFKC) | `unicodedata.normalize("NFC", text)` handles combining characters, ligature normalization |
| `re` (stdlib) | Dehyphenation, line break collapse, punctuation fixes | Regex patterns for `word-\nword` rejoining, multiple newline collapse |
| `textwrap` (stdlib) | Optional paragraph reformatting | Only if RAG consumers need reflowed text |

**Why no library:**
- `ftfy` (fix text encoding) -- Overkill. OCR output is UTF-8 from ocrmypdf/marker. The problems are layout artifacts (hyphenation, line breaks), not encoding issues.
- `unidecode` -- Wrong tool. We want to preserve Unicode (academic Greek, German umlauts), not transliterate to ASCII.

**Architecture:** New `postprocess.py` module with a pipeline of composable transforms:
```python
# Each transform: str -> str, composable via simple chaining
TRANSFORMS = [normalize_unicode, dehyphenate, collapse_linebreaks, fix_punctuation_spacing]
```

### 2. Multiprocess Structured Logging

**Stack: Python stdlib only**

| Module | Purpose | Notes |
|--------|---------|-------|
| `logging` (stdlib) | Core logging framework | Already used in mcp_server.py |
| `logging.handlers.QueueHandler` (stdlib) | Send logs from worker processes to main process | Available since Python 3.2 |
| `logging.handlers.QueueListener` (stdlib) | Receive logs in main process, dispatch to handlers | Pairs with QueueHandler |
| `multiprocessing.Queue` (stdlib) | Cross-process log transport | Thread/process safe |
| `json` (stdlib) | Structured JSON log formatting | Custom `logging.Formatter` subclass |

**Why no library:**
- `structlog` -- Good library but overkill for this use case. We need one thing: route worker logs to main process in structured format. stdlib QueueHandler does exactly this.
- `python-json-logger` -- Just a custom Formatter. Writing a 15-line JSONFormatter is simpler than adding a dependency.

**Pattern:**
```python
# Main process: QueueListener with JSONFormatter -> file handler
# Worker processes: QueueHandler -> multiprocessing.Queue
# Result: All logs centralized, structured, ordered
```

### 3. MCP Async Job Handling / Timeout Resilience

**Stack: Python stdlib only**

| Module | Purpose | Notes |
|--------|---------|-------|
| `asyncio` (stdlib) | Async timeout wrapping, background tasks | Already used in mcp_server.py (`asyncio.to_thread`) |
| `concurrent.futures` (stdlib) | Future-based job tracking | Already used in pipeline.py (`ProcessPoolExecutor`) |
| `uuid` (stdlib) | Job ID generation | `uuid.uuid4()` for async job identifiers |

**Why no library:**
- MCP SDK (`mcp[cli]`) already provides the async framework via FastMCP. The timeout/job pattern is just wrapping `asyncio.to_thread` with `asyncio.wait_for` and a job registry dict.
- No need for Celery, dramatiq, or any task queue -- MCP is single-user, in-process.

**Pattern:**
```python
# Job registry: dict[str, AsyncJob] where AsyncJob tracks status/result
# Start: asyncio.create_task(run_with_timeout(pipeline, config))
# Poll: Return job status from registry
# Timeout: asyncio.wait_for(task, timeout=seconds)
```

### 4. Environment Validation

**Stack: Python stdlib only**

| Module | Purpose | Notes |
|--------|---------|-------|
| `shutil.which` (stdlib) | Check binary availability (tesseract, ghostscript) | Returns path or None |
| `subprocess` (stdlib) | Version checking (`tesseract --version`) | Already implicitly used via ocrmypdf |
| `importlib.metadata` (stdlib) | Check Python package versions | `version("ocrmypdf")` etc. |

**Why no library:** This is 30 lines of code checking 3-4 binaries and packages exist. No framework needed.

### 5. Work Directory Cleanup

**Stack: Python stdlib only**

| Module | Purpose | Notes |
|--------|---------|-------|
| `tempfile` (stdlib) | Managed temp directories | `tempfile.TemporaryDirectory` with context manager |
| `atexit` (stdlib) | Cleanup on abnormal exit | Belt-and-suspenders with context manager |
| `pathlib` (stdlib) | Path operations | Already used throughout |

### 6. JSON Metadata Output

**Stack: Python stdlib only**

| Module | Purpose | Notes |
|--------|---------|-------|
| `json` (stdlib) | Serialize quality metadata | Already have `to_dict()` on results |
| `dataclasses.asdict` (stdlib) | Convert dataclasses to dicts | Already used pattern |

## What NOT to Add

| Library | Why Tempting | Why Wrong for This Project |
|---------|-------------|---------------------------|
| `structlog` | Structured logging is trendy | QueueHandler + 15-line JSONFormatter does the same thing with zero deps |
| `ftfy` | "Fix text" sounds relevant | OCR text isn't encoding-broken, it has layout artifacts. Different problem. |
| `pydantic` | Config validation | Dataclasses are sufficient. Config is simple and internal. Not worth the dep for v2.0. |
| `click` | CLI framework | Previous research recommended this. Defer -- argparse works, v2.0 scope is post-processing not CLI rewrite. |
| `celery`/`dramatiq` | Job queue for MCP | Single-user tool. asyncio dict-based job registry is correct. |
| `tenacity` | Retry logic | If needed, a 10-line retry decorator suffices. Don't add a dep for one call site. |

## Changes to pyproject.toml

**None.** No new dependencies for v2.0 features.

The only change is new modules within `src/scholardoc_ocr/`:

| New Module | Purpose |
|------------|---------|
| `postprocess.py` | Text post-processing pipeline (dehyphenation, unicode, line breaks) |
| `logging_config.py` | QueueHandler setup, JSONFormatter, structured logging |
| `validation.py` | Environment validation (binaries, packages, versions) |

## Dev Dependencies to Consider

| Package | Purpose | Priority |
|---------|---------|----------|
| `pytest-asyncio` | Test async MCP job handling | Add if not already testable |

```bash
# Only dev dep addition
pip install -e ".[dev]"  # no changes to production deps
```

## Integration Points with Existing Stack

| Existing Module | v2.0 Integration |
|----------------|-----------------|
| `pipeline.py` | Calls `postprocess.py` after OCR, before writing output. Initializes QueueHandler logging for workers. |
| `mcp_server.py` | Wraps `asyncio.to_thread` call with timeout + job registry. Calls `validation.py` on startup. |
| `quality.py` | QualityResult already has `to_dict()` -- feeds directly into JSON metadata output. |
| `processor.py` | Workers use QueueHandler instead of direct logging. |
| `types.py` | Add `PostProcessConfig` dataclass (which transforms to apply). |

## Sources

- Python 3.11 stdlib documentation (HIGH confidence -- verified `logging.handlers.QueueHandler`, `unicodedata`, `shutil.which` availability)
- Existing codebase analysis (`pyproject.toml`, `mcp_server.py`, `quality.py`, `pipeline.py`)
- v1.0 STACK.md research (2026-01-28)
