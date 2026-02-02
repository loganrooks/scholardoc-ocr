# Architecture Patterns: v2.0 Integration

**Project:** scholardoc-ocr v2.0
**Researched:** 2026-02-02
**Confidence:** HIGH (based on direct codebase analysis)

## Current Architecture (Post v1.0 Refactor)

```
cli.py (argparse + Rich) ──┐
                            ├──> pipeline.py (run_pipeline) ──> BatchResult
mcp_server.py (FastMCP) ───┘         │
                                     ├── _tesseract_worker (ProcessPoolExecutor)
                                     │       └── processor.py, quality.py, tesseract.py
                                     └── surya phase (main process, sequential per-file)
                                             └── surya.py

types.py       -- FileResult, PageResult, BatchResult, OCREngine
callbacks.py   -- PipelineCallback protocol, LoggingCallback, NullCallback
cli.py         -- RichCallback
exceptions.py  -- Custom exceptions
quality.py     -- QualityAnalyzer (regex scoring)
confidence.py  -- Signal-based confidence
dictionary.py  -- Academic term whitelist
```

Key constraint: `run_pipeline(config, callback)` is the single entry point for both CLI and MCP. All v2.0 features must integrate through or alongside this function, not bypass it.

## v2.0 New Components

### 1. Post-Processing Module (`postprocess.py`) -- NEW FILE

**Integration point:** After OCR text extraction, before final output write. Text is currently written at two places in `_tesseract_worker` (lines 93 and 162) and updated in the Surya phase (line 391).

**Design:**

```python
@dataclass
class PostProcessConfig:
    dehyphenate: bool = True
    normalize_unicode: bool = True
    fix_ligatures: bool = True
    fix_line_breaks: bool = True
    fix_punctuation: bool = True

class TextPostProcessor:
    def __init__(self, config: PostProcessConfig | None = None): ...
    def process(self, text: str) -> str: ...
    def process_page(self, text: str) -> str: ...
    def process_pages(self, pages: list[str]) -> list[str]: ...
```

**Rationale:**
- Callable independently (library-first): `TextPostProcessor().process(text)`
- Stateless -- no dependency on pipeline types
- Config dataclass matches existing pattern (PipelineConfig, TesseractConfig, SuryaConfig)
- Takes and returns strings, not PageResult -- keeps it composable

**Pipeline integration:**
- Add `post_process: bool = True` and `post_process_config: PostProcessConfig | None` to `PipelineConfig`
- Apply in `_tesseract_worker` after text extraction, before writing .txt
- Apply in Surya phase after `surya_markdown` is produced
- Process text in place -- no need to store raw + processed separately

**Dependencies:** ZERO. Pure text transforms. Build first.

### 2. Structured Multiprocess Logging (`logging_config.py`) -- NEW FILE

**Problem:** Worker processes each use module-level loggers. Logs interleave without structure. No JSON output. MCP server uses a manual `_log()` file-write hack.

**Pattern: QueueHandler + ProcessPoolExecutor initializer**

```python
def setup_logging(
    level: int = logging.INFO,
    json_output: bool = False,
    log_file: Path | None = None,
) -> tuple[Queue, QueueListener]:
    """Configure logging. Returns queue + listener for worker processes."""
    ...

def worker_logging_init(queue: Queue) -> None:
    """Initializer for ProcessPoolExecutor workers."""
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(QueueHandler(queue))
    root.setLevel(logging.DEBUG)

def shutdown_logging(listener: QueueListener) -> None:
    """Stop the QueueListener."""
    listener.stop()
```

**Integration points:**
- `run_pipeline()`: Create queue, pass to `ProcessPoolExecutor(initializer=worker_logging_init, initargs=(queue,))`
- `cli.py main()`: Call `setup_logging()` instead of `logging.basicConfig()`
- `mcp_server.py main()`: Call `setup_logging(json_output=True)` instead of manual `_log()` hack

**Key detail:** Use `ProcessPoolExecutor(initializer=...)` rather than passing queue through `config_dict`. Runs once per worker process, not per task. Keeps config_dict clean.

**`multiprocessing.Queue` is picklable.** Standard `queue.Queue` is NOT. Use the multiprocessing version.

### 3. MCP Async Job Handling -- MODIFY `mcp_server.py`

**Problem:** Current `ocr()` runs via `asyncio.to_thread()`. Large batches may timeout the MCP client.

**Design:**

```python
_jobs: dict[str, JobStatus] = {}  # In-memory, ephemeral

@dataclass
class JobStatus:
    job_id: str
    status: str  # "pending" | "running" | "complete" | "failed"
    created: float
    result: dict | None = None
    error: str | None = None
    progress: dict | None = None

@mcp.tool()
async def ocr_async(input_path: str, ...) -> dict:
    """Start OCR job, return job ID immediately."""
    job_id = uuid4().hex[:8]
    _jobs[job_id] = JobStatus(...)
    asyncio.create_task(_run_ocr_job(job_id, ...))
    return {"job_id": job_id, "status": "pending"}

@mcp.tool()
async def ocr_status(job_id: str) -> dict:
    """Check job status and results."""
    ...

@mcp.tool()
async def ocr_jobs() -> dict:
    """List all jobs."""
    ...
```

**Callback integration:** Create `AsyncJobCallback` implementing `PipelineCallback` that updates `_jobs[job_id].progress`. The protocol already exists -- this is a clean fit.

**Thread safety:** `run_pipeline()` runs in a thread via `asyncio.to_thread`. Dict writes for status updates are atomic enough under CPython GIL. No lock needed for simple field assignments.

**Keep existing `ocr()` tool unchanged** for backward compatibility. Add `ocr_async`, `ocr_status`, `ocr_jobs` as new tools.

### 4. Environment Validation (`environment.py`) -- NEW FILE

```python
@dataclass
class EnvironmentCheck:
    name: str
    available: bool
    version: str | None = None
    error: str | None = None

def validate_environment(require_surya: bool = False) -> list[EnvironmentCheck]:
    """Check tesseract, ocrmypdf, ghostscript, optionally surya."""
    ...

def require_environment(require_surya: bool = False) -> None:
    """Validate and raise EnvironmentError if critical tools missing."""
    ...
```

**Integration:** Call at entry points only.
- `cli.py main()`: `require_environment()` before `run_pipeline()`
- `mcp_server.py`: Lazy on first `ocr()` call
- `run_pipeline()`: Do NOT call here -- keep pipeline free of startup concerns

**Dependencies:** ZERO. Build anytime.

### 5. Work Directory Cleanup -- MODIFY `pipeline.py`

Three-line change at end of `run_pipeline()`:

```python
if not config.debug:
    work_dir = config.output_dir / "work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
```

Add `keep_work_dir: bool = False` to `PipelineConfig`. Trivial.

### 6. JSON Metadata Output -- MODIFY `pipeline.py` + `_tesseract_worker`

**Infrastructure already exists:** `BatchResult.to_dict()` and `to_json()` are in types.py.

**What to add:**
- In `_tesseract_worker`: Write `{stem}.json` alongside .txt and .pdf in final/
- At end of `run_pipeline()`: Write `batch_metadata.json`
- In `cli.py`: Add `--json` flag for stdout JSON instead of Rich table

## Component Dependency Graph

```
environment.py          (independent)
postprocess.py          (independent)
    │
    ▼
pipeline.py changes     (integrates postprocess, cleanup, JSON output)
    │
    ▼
logging_config.py       (needs pipeline.py worker init changes)
    │
    ▼
mcp_server.py changes   (needs stable pipeline + logging)
    │
    ▼
cli.py changes          (needs all above)
```

## Recommended Build Order

| Order | Component | Rationale |
|-------|-----------|-----------|
| 1 | `environment.py` | Zero deps, immediate value, easy win |
| 2 | `postprocess.py` | Zero deps, pure text transforms, excellent test surface |
| 3 | Pipeline integration (postprocess + cleanup + JSON) | Single pass modifying pipeline.py |
| 4 | `logging_config.py` + pipeline worker init | Touches ProcessPoolExecutor setup |
| 5 | MCP async jobs | Needs stable pipeline + logging |
| 6 | CLI updates (--json, env check) | Final integration layer |

## Data Flow: v2.0

```
CLI / MCP Server
    |
    +-- validate_environment()          [NEW: fail fast]
    +-- setup_logging()                 [NEW: structured logs]
    |
    +-- run_pipeline(config, callback)
            |
            +-- Phase 1: ProcessPoolExecutor(initializer=worker_logging_init)
            |     +-- _tesseract_worker()
            |           +-- OCR (existing)
            |           +-- post_process(text)     [NEW]
            |           +-- write .txt, .pdf
            |           +-- write .json metadata   [NEW]
            |
            +-- Phase 2: Surya (existing)
            |     +-- post_process(surya_text)     [NEW]
            |
            +-- Write batch_metadata.json          [NEW]
            +-- Cleanup work dir                   [NEW]
```

## Anti-Patterns to Avoid

### Do not add post-processing inside PageResult/FileResult
Post-processing is a transform on text, not a property of results. Keep result types as data carriers. Process text before storing it.

### Do not make logging a required parameter of run_pipeline
Keep `run_pipeline(config, callback)` signature. Logging setup happens in the caller (CLI, MCP server). Workers configure via initializer.

### Do not store MCP jobs in a database
MCP server is single-process. In-memory dict is correct. Jobs are ephemeral. SQLite adds complexity for zero benefit.

### Do not validate environment inside the pipeline
Fail fast at entry points. Do not let users wait through file discovery and worker spawning to discover ghostscript is missing.

### Do not try to parallelize Surya across processes
PyTorch GPU models cannot be shared across ProcessPoolExecutor workers (CUDA context is per-process). Surya runs in main process, uses GPU parallelism internally. This is correct and intentional.

## Existing Patterns to Preserve

| Pattern | Where | Why |
|---------|-------|-----|
| `PipelineCallback` protocol | callbacks.py | Clean separation of progress reporting from logic |
| Config dataclasses | pipeline.py, tesseract.py, surya.py | Type-safe, picklable configuration |
| `to_dict()` / `to_json()` on result types | types.py | Serialization already built in |
| Library-first design | pipeline.py exports `run_pipeline()` | CLI and MCP both call same function |
| Surya in main process | pipeline.py Phase 2 | GPU model constraint |

## Sources

- Direct codebase analysis of all modules (HIGH confidence)
- Python `logging.handlers.QueueHandler` documentation (HIGH confidence)
- Python `concurrent.futures.ProcessPoolExecutor` initializer parameter (HIGH confidence)
- CPython GIL behavior for dict writes (HIGH confidence, well-established)
