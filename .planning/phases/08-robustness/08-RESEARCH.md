# Phase 8: Robustness - Research

**Researched:** 2026-02-02
**Domain:** Python multiprocess logging, environment validation, cleanup, timeouts
**Confidence:** HIGH

## Summary

Phase 8 adds operational reliability to the OCR pipeline: structured logging that works across process boundaries, environment pre-checks, work directory lifecycle management, and timeout protection. All requirements use Python stdlib -- no new dependencies needed.

The codebase already uses `logging.getLogger(__name__)` throughout and `ProcessPoolExecutor` for Tesseract workers. The core challenge is that Python's `logging` module handlers are not fork-safe: worker processes inherit the parent's logger config but their handlers write to different file descriptors. The standard solution is `QueueHandler`/`QueueListener` from `logging.handlers`.

**Primary recommendation:** Use stdlib `logging.handlers.QueueHandler` + `QueueListener` with a `multiprocessing.Queue`, validate environment in a dedicated `validate_environment()` function called before pipeline dispatch, and wrap worker submissions with `concurrent.futures` timeout.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `logging.handlers.QueueHandler` | stdlib | Send log records from workers to main process | Python's official solution for multiprocess logging |
| `logging.handlers.QueueListener` | stdlib | Receive and dispatch log records in main process | Pairs with QueueHandler |
| `multiprocessing.Queue` | stdlib | Transport for log records across processes | Fork-safe, works on macOS |
| `shutil.which` | stdlib | Find tesseract binary on PATH | Standard binary lookup |
| `shutil.rmtree` | stdlib | Remove work directory tree | Already used in codebase |
| `concurrent.futures.Future.result(timeout=)` | stdlib | Per-file timeout protection | Built into executor API |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `subprocess.run` | stdlib | Query `tesseract --version`, `tesseract --list-langs` | Environment validation |
| `tempfile.gettempdir` | stdlib | Identify and test TMPDIR | Startup validation |
| `logging.handlers.RotatingFileHandler` | stdlib | Per-worker log files | ROBU-07 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| QueueHandler/Listener | `structlog` | Adds dependency; stdlib sufficient for this scale |
| `shutil.which` | Manual PATH walk | No reason to hand-roll |
| Future.result(timeout) | `signal.alarm` | signal not safe in threads; Future timeout is cleaner |

**Installation:** No new packages required.

## Architecture Patterns

### Recommended Changes
```
src/scholardoc_ocr/
  cli.py          # Add --keep-intermediates, --timeout flags
  pipeline.py     # Add logging setup, env validation, cleanup, timeout
  processor.py    # No changes needed
  quality.py      # No changes needed
  logging_.py     # NEW: QueueHandler/Listener setup, per-worker file handlers
  environment.py  # NEW: validate_environment(), startup diagnostics
```

### Pattern 1: Multiprocess Logging with QueueHandler/QueueListener
**What:** Workers push `LogRecord` objects onto a `multiprocessing.Queue`. Main process runs a `QueueListener` that dispatches them to real handlers (console, file).
**When to use:** Any time `ProcessPoolExecutor` workers need to log.
**Example:**
```python
import logging
import logging.handlers
import multiprocessing as mp

def setup_mp_logging() -> tuple[mp.Queue, logging.handlers.QueueListener]:
    """Set up cross-process logging. Call in main process before spawning workers."""
    log_queue = mp.Queue(-1)  # unbounded
    # Handlers that the listener dispatches to
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    )
    listener = logging.handlers.QueueListener(
        log_queue, console_handler, respect_handler_level=True
    )
    listener.start()
    return log_queue, listener

def configure_worker_logging(log_queue: mp.Queue) -> None:
    """Call at the start of each worker process."""
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(logging.handlers.QueueHandler(log_queue))
    root.setLevel(logging.DEBUG)
```

### Pattern 2: Worker Initializer for ProcessPoolExecutor
**What:** Pass `initializer` and `initargs` to `ProcessPoolExecutor` to run logging setup once per worker.
**Example:**
```python
with ProcessPoolExecutor(
    max_workers=pool_workers,
    initializer=configure_worker_logging,
    initargs=(log_queue,),
) as executor:
    ...
```

### Pattern 3: Environment Validation
**What:** Check all external dependencies before starting expensive work.
**Example:**
```python
import shutil
import subprocess
import tempfile

def validate_environment() -> list[str]:
    """Return list of errors. Empty = all good."""
    errors = []

    # Tesseract binary
    tess = shutil.which("tesseract")
    if not tess:
        errors.append("tesseract not found on PATH")
    else:
        # Check language packs
        result = subprocess.run(
            [tess, "--list-langs"], capture_output=True, text=True
        )
        available = set(result.stdout.strip().split("\n")[1:])  # skip header
        for lang in required_langs:
            if lang not in available:
                errors.append(f"tesseract language pack missing: {lang}")

    # TMPDIR writable
    tmpdir = tempfile.gettempdir()
    if not os.access(tmpdir, os.W_OK):
        errors.append(f"TMPDIR not writable: {tmpdir}")

    return errors
```

### Pattern 4: Work Directory Cleanup
**What:** Remove `output_dir/work/` after successful completion unless `--keep-intermediates`.
**Example:**
```python
# At end of run_pipeline(), after all processing:
if not config.keep_intermediates:
    work_dir = config.output_dir / "work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
        logger.info("Cleaned up work directory: %s", work_dir)
```

### Pattern 5: Worker Timeout via Future.result()
**What:** Use the `timeout` parameter on `Future.result()` to kill hung workers.
**Example:**
```python
for future in as_completed(future_to_path):
    path = future_to_path[future]
    try:
        result = future.result(timeout=config.timeout_seconds)
    except TimeoutError:
        future.cancel()
        logger.error("%s: timed out after %ds", path.name, config.timeout_seconds)
        file_results.append(FileResult(
            filename=path.name, success=False, engine=OCREngine.NONE,
            quality_score=0.0, page_count=0, pages=[],
            error=f"Timed out after {config.timeout_seconds}s",
        ))
```

**Important caveat:** `Future.cancel()` only prevents a not-yet-started task. For an already-running worker process, the future will raise `TimeoutError` but the worker keeps running until the pool shuts down. True cancellation of in-flight `ProcessPoolExecutor` work requires shutting down the executor. For this project, the timeout is primarily a reporting mechanism -- the executor's context manager will clean up on exit.

### Anti-Patterns to Avoid
- **Configuring logging in each worker function call:** Use `initializer` instead -- it runs once per worker process, not once per task.
- **Using `multiprocessing.log_to_stderr()`:** This is a debug tool, not a production logging solution.
- **Catching exceptions without traceback:** Always use `traceback.format_exc()` or `logger.exception()`.
- **fork start method on macOS with logging:** macOS defaults to `spawn` since Python 3.8. This is fine for QueueHandler. Do NOT switch to `fork` -- it causes hangs with macOS frameworks.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cross-process log transport | Custom socket/pipe logger | `QueueHandler` + `QueueListener` | Handles serialization, thread safety, backpressure |
| Binary lookup on PATH | Manual `os.environ["PATH"].split()` | `shutil.which()` | Handles platform differences |
| Recursive directory deletion | Manual `os.walk` + `os.remove` | `shutil.rmtree()` | Already in stdlib, handles edge cases |
| Timeout on worker tasks | `signal.alarm` or threading timer | `Future.result(timeout=)` | Designed for exactly this use case |

**Key insight:** Every requirement in this phase maps directly to a stdlib facility. There is zero reason for external dependencies.

## Common Pitfalls

### Pitfall 1: QueueHandler in fork-unsafe context
**What goes wrong:** On macOS with `fork` start method, the Queue can deadlock because forked processes inherit locks in unknown state.
**Why it happens:** macOS has deprecated `fork` for multiprocessing.
**How to avoid:** Use the default `spawn` start method (Python 3.8+ default on macOS). Do not set `mp.set_start_method("fork")`.
**Warning signs:** Hangs during worker startup with no error message.

### Pitfall 2: QueueListener not stopped
**What goes wrong:** Program hangs on exit because QueueListener's internal thread is still running.
**Why it happens:** QueueListener.start() creates a daemon thread, but if the queue has pending items the thread may block.
**How to avoid:** Always call `listener.stop()` in a finally block or use it as a context manager pattern.
**Warning signs:** Program doesn't exit cleanly after Ctrl+C.

### Pitfall 3: Worker logging before initializer runs
**What goes wrong:** First log message from worker goes to inherited (broken) handler.
**Why it happens:** Module-level code that logs during import.
**How to avoid:** Ensure worker modules don't log at import time. The `_tesseract_worker` function already does lazy imports, which is correct.
**Warning signs:** Duplicate or missing log messages from workers.

### Pitfall 4: Future.result(timeout) doesn't kill the worker
**What goes wrong:** Developer expects timeout to terminate the worker process; it doesn't.
**Why it happens:** `ProcessPoolExecutor` reuses worker processes. Timeout only affects the caller waiting for the result.
**How to avoid:** Document this limitation. For true cancellation, the worker itself must check an `Event` or the task must be designed to complete in bounded time (ocrmypdf already has `tesseract_timeout`).
**Warning signs:** Worker processes consuming CPU after timeout is reported.

### Pitfall 5: `str(e)` on exceptions with empty message
**What goes wrong:** Error message is empty string, losing all diagnostic info.
**Why it happens:** Some exceptions (e.g., `OSError` subclasses) have empty `str()`.
**How to avoid:** Always use `f"{type(e).__name__}: {e!r}"` or `traceback.format_exc()`.
**Warning signs:** Error logs that say "Error: " with nothing after it.

### Pitfall 6: Cleaning work dir before Surya phase completes
**What goes wrong:** Work directory deleted after Phase 1 but Phase 2 (Surya) may need intermediate files.
**Why it happens:** Cleanup added at wrong point in pipeline.
**How to avoid:** Cleanup must happen after ALL phases complete, at the very end of `run_pipeline()`.
**Warning signs:** Surya phase fails with FileNotFoundError.

## Code Examples

### Complete Logging Setup
```python
# logging_.py
import logging
import logging.handlers
import multiprocessing as mp
import os
from pathlib import Path


def setup_pipeline_logging(
    log_dir: Path | None = None,
    level: int = logging.INFO,
) -> tuple[mp.Queue, logging.handlers.QueueListener]:
    """Initialize multiprocess-safe logging.

    Returns (queue, listener). Caller must stop listener when done.
    """
    log_queue = mp.Queue(-1)

    handlers: list[logging.Handler] = []

    # Console handler
    console = logging.StreamHandler()
    console.setLevel(level)
    console.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    ))
    handlers.append(console)

    # Per-worker file handler (ROBU-07)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(
            log_dir / f"worker-{os.getpid()}.log"
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(process)d | %(name)s | %(message)s"
        ))
        handlers.append(file_handler)

    listener = logging.handlers.QueueListener(
        log_queue, *handlers, respect_handler_level=True
    )
    listener.start()
    return log_queue, listener
```

### Worker Initializer
```python
def _worker_init(log_queue: mp.Queue, log_dir: Path | None = None) -> None:
    """Initialize logging in worker process."""
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(logging.handlers.QueueHandler(log_queue))
    root.setLevel(logging.DEBUG)

    # Optional per-worker file (ROBU-07)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_dir / f"worker-{os.getpid()}.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        ))
        root.addHandler(fh)
```

### Startup Diagnostic Report (ROBU-08)
```python
def log_startup_diagnostics(config: PipelineConfig) -> None:
    """Log environment info for debugging."""
    import platform
    import subprocess
    import tempfile

    logger.info("Python %s on %s", platform.python_version(), platform.platform())
    logger.info("TMPDIR: %s", tempfile.gettempdir())

    tess = shutil.which("tesseract")
    if tess:
        ver = subprocess.run([tess, "--version"], capture_output=True, text=True)
        logger.info("Tesseract: %s", ver.stdout.split("\n")[0])
        langs = subprocess.run([tess, "--list-langs"], capture_output=True, text=True)
        logger.info("Tesseract langs: %s", langs.stdout.strip())
    else:
        logger.warning("Tesseract: NOT FOUND")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `multiprocessing.log_to_stderr()` | `QueueHandler`/`QueueListener` | Python 3.2+ | Proper structured multiprocess logging |
| `fork` on macOS | `spawn` (default since 3.8) | Python 3.8 | No more fork-related deadlocks |
| Manual process timeout with signals | `Future.result(timeout=)` | Python 3.2+ | Clean timeout API |

## Open Questions

1. **Per-worker log files location**
   - What we know: ROBU-07 wants per-worker logs with PID prefix
   - What's unclear: Should they go in the work dir (cleaned up) or a separate logs dir?
   - Recommendation: Put them in `output_dir/logs/` which persists. Work dir is for intermediate PDFs.

2. **Timeout default value**
   - What we know: ocrmypdf already has `tesseract_timeout=600` per page. ROBU-06 wants per-file timeout.
   - What's unclear: What's a reasonable default for an entire file?
   - Recommendation: Default 1800s (30 min) per file. Academic PDFs can be 500+ pages.

3. **`str(e)` in as_completed error handler (line 304)**
   - What we know: Pipeline line 304 uses bare `str(e)` which loses traceback
   - ROBU-03 requires this to be fixed
   - Recommendation: Use `traceback.format_exception()` or at minimum `f"{type(e).__name__}: {e!r}"`

## Sources

### Primary (HIGH confidence)
- Python stdlib `logging.handlers` docs -- QueueHandler/QueueListener API
- Python stdlib `concurrent.futures` docs -- Future.result(timeout) behavior
- Python stdlib `shutil.which` docs
- Codebase inspection: `pipeline.py`, `cli.py`, `processor.py`, `tesseract.py`

### Secondary (MEDIUM confidence)
- Python 3.8 release notes on macOS spawn default
- ocrmypdf docs on tesseract_timeout parameter

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All stdlib, well-documented APIs
- Architecture: HIGH - Patterns are standard Python multiprocessing logging
- Pitfalls: HIGH - Well-known issues with macOS fork, QueueListener lifecycle

**Research date:** 2026-02-02
**Valid until:** 2026-05-02 (stable stdlib APIs, no expiry concern)
