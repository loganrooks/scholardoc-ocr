# Phase 10: Output and MCP - Research

**Researched:** 2026-02-02
**Domain:** JSON output, CLI flags, MCP async job handling
**Confidence:** HIGH

## Summary

This phase adds structured output formats (JSON metadata files, `--json` stdout, `--extract-text` CLI flag) and MCP async job handling. The codebase already has most of the infrastructure: `to_dict()`/`to_json()` on all result types, an existing MCP server with `ocr()` tool, and a callback system for progress reporting.

The key insight is that OUTP-01, OUTP-02, and OUTP-05 are straightforward additions to existing code, while OUTP-03/OUTP-04 (MCP async jobs) require understanding the MCP SDK's experimental task support or implementing a simpler in-process job store.

**Primary recommendation:** Use existing `BatchResult.to_dict()` for JSON output. For MCP async, use an in-process job store with `asyncio.create_task()` rather than the experimental MCP task API (which requires Streamable HTTP transport, not stdio).

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| json (stdlib) | - | JSON serialization | Already used via `BatchResult.to_json()` |
| mcp[cli] | existing | MCP server | Already installed as optional dep |
| asyncio (stdlib) | - | Async job management | Already used in mcp_server.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| uuid (stdlib) | - | Job ID generation | For OUTP-03 async job IDs |
| dataclasses (stdlib) | - | Job state storage | For async job tracking |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| In-process job store | MCP experimental tasks API | Tasks API requires Streamable HTTP transport + is experimental; stdio transport (used by Claude Desktop) doesn't support it. In-process dict is simpler and works now. |
| uuid4 job IDs | Incrementing int IDs | UUID avoids collisions if server restarts; either works for single-process |

## Architecture Patterns

### Current State Analysis

**What already exists:**
1. `types.py` — `BatchResult.to_dict(include_text=False)`, `FileResult.to_dict()`, `PageResult.to_dict()` all serialize to JSON-compatible dicts. `BatchResult.to_json()` produces JSON string.
2. `mcp_server.py` — `ocr()` tool already runs pipeline via `asyncio.to_thread()`, returns dict. Already has `extract_text` param (but re-extracts from PDF instead of using pipeline's .txt output).
3. `pipeline.py` — Already writes `.txt` files to `final/` dir during processing (both existing-text and tesseract paths). Text is already post-processed.
4. `callbacks.py` — `PipelineCallback` protocol with `on_progress`, `on_phase`, `on_model` events.
5. `cli.py` — Entry point with argparse, `RichCallback`.

### Pattern 1: JSON Metadata File (OUTP-01)
**What:** Write a `.json` file alongside each output PDF in `final/` containing per-page quality scores, engine provenance, and processing stats.
**Where:** In `_tesseract_worker()` after writing PDF/TXT to `final/`, and in `run_pipeline()` after Surya phase updates page results.
**Key decision:** Write JSON at end of pipeline (after Surya updates), not in the worker. The worker writes preliminary results; Surya phase mutates `FileResult.pages` in-place. So JSON must be written after Phase 2 completes.

```python
# In run_pipeline(), after Surya phase and before cleanup:
final_dir = config.output_dir / "final"
for file_result in file_results:
    if file_result.success:
        metadata = file_result.to_dict(include_text=False)
        metadata["pipeline_version"] = "0.1.0"
        json_path = final_dir / f"{Path(file_result.filename).stem}.json"
        json_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
```

### Pattern 2: --extract-text Flag (OUTP-02)
**What:** CLI flag that produces `.txt` alongside output PDF.
**Current state:** Pipeline ALREADY writes `.txt` files to `final/` during processing. The `_tesseract_worker` writes post-processed text. So `--extract-text` may just need to control whether `.txt` is kept or deleted.
**Key insight:** Text extraction is already happening. The flag should either (a) be the default behavior (already is), or (b) control whether to clean up `.txt` files if the user doesn't want them. Current behavior: `.txt` is always written. The requirement says "triggers" extraction, implying it's opt-in. So the change is: only write `.txt` when `extract_text=True` in config, or always write internally but delete at end unless flag is set.
**Recommendation:** Keep always-write-internally (pipeline needs text for quality analysis), but only preserve `.txt` in `final/` when `--extract-text` is set. This means adding a cleanup step.

### Pattern 3: --json Flag (OUTP-05)
**What:** Output structured JSON results to stdout.
**Implementation:** After `run_pipeline()` returns `BatchResult`, if `--json` flag is set, print `batch.to_json()` to stdout and skip Rich table summary. Suppress Rich progress output when `--json` is active (use `NullCallback` or `LoggingCallback`).

```python
if args.json:
    print(batch.to_json(include_text=args.extract_text))
    sys.exit(0 if batch.error_count == 0 else 1)
```

### Pattern 4: MCP Async Jobs (OUTP-03, OUTP-04)
**What:** `ocr_async()` returns job ID immediately; `ocr_status(job_id)` checks progress.
**Architecture:** In-process dict mapping job_id -> job state. `ocr_async()` spawns `asyncio.create_task()` wrapping the existing `asyncio.to_thread(run_pipeline, ...)` call. A custom callback bridges pipeline events to the job state dict.

```python
import uuid
from dataclasses import dataclass, field

@dataclass
class JobState:
    job_id: str
    status: str = "running"  # running | completed | failed
    progress: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None

_jobs: dict[str, JobState] = {}

@mcp.tool()
async def ocr_async(...) -> dict:
    job_id = str(uuid.uuid4())
    job = JobState(job_id=job_id)
    _jobs[job_id] = job
    asyncio.create_task(_run_job(job, config))
    return {"job_id": job_id, "status": "running"}

@mcp.tool()
async def ocr_status(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        return {"error": f"Unknown job: {job_id}"}
    return {"job_id": job.job_id, "status": job.status,
            "progress": job.progress, "result": job.result}
```

### Pattern 5: MCP Progress Events (OUTP-04)
**What:** Emit progress during processing.
**Implementation:** Use MCP Context's `report_progress()` and `ctx.info()` for the synchronous `ocr()` tool. For `ocr_async()`, progress is stored in `JobState.progress` dict and retrieved via `ocr_status()`.
**Limitation:** `report_progress` only works when the client supports it and the tool has a `ctx: Context` parameter. The existing `ocr()` tool can be enhanced to accept `ctx` and report progress via a bridging callback.

```python
@mcp.tool()
async def ocr(input_path: str, ctx: Context[ServerSession, None], ...) -> dict:
    # Create a callback that bridges to MCP progress
    class MCPCallback:
        def on_progress(self, event):
            # Can't await in sync callback, but we can store state
            pass
        def on_phase(self, event): pass
        def on_model(self, event): pass

    # Pipeline runs in thread, so progress bridging is limited
    result = await asyncio.to_thread(run_pipeline, config, MCPCallback())
```

**Key limitation:** `report_progress` is async but the pipeline callback runs in a thread via `asyncio.to_thread()`. Bridging requires thread-safe communication (e.g., the callback posts to an asyncio queue, a coroutine reads and calls `ctx.report_progress()`). This adds complexity. A simpler approach: just report progress in `ocr_status()` for async jobs, and accept that synchronous `ocr()` can't report mid-execution progress easily.

### Anti-Patterns to Avoid
- **Writing JSON in the worker process:** Surya phase mutates results after workers finish. JSON must be written after all processing is complete.
- **Re-extracting text from PDF for --extract-text:** Pipeline already extracts and post-processes text. The MCP server currently re-extracts via PyMuPDF, losing post-processing. Fix this.
- **Blocking MCP event loop:** Always use `asyncio.to_thread()` for pipeline execution (already done).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON serialization | Custom serializer | Existing `to_dict()` + `json.dumps()` | Already implemented on all result types |
| Job ID generation | Custom ID scheme | `uuid.uuid4()` | Standard, collision-free |
| Progress reporting in MCP | Custom protocol | `ctx.report_progress()` | Built into MCP SDK |

## Common Pitfalls

### Pitfall 1: JSON Written Before Surya Updates
**What goes wrong:** Writing per-file JSON in `_tesseract_worker` produces metadata that doesn't reflect Surya enhancements.
**Why it happens:** Workers run in Phase 1; Surya updates `FileResult.pages` in-place during Phase 2.
**How to avoid:** Write all JSON metadata after Phase 2 completes, in `run_pipeline()`.

### Pitfall 2: MCP extract_text Duplicates Pipeline Work
**What goes wrong:** Current `mcp_server.py` re-extracts text from output PDF via PyMuPDF when `extract_text=True`, losing post-processing transforms (dehyphenation, paragraph joining, etc.).
**Why it happens:** MCP server was written before post-processing pipeline existed.
**How to avoid:** Use the `.txt` file already written by the pipeline instead of re-extracting.

### Pitfall 3: Text Files Always Written
**What goes wrong:** Pipeline currently always writes `.txt` to `final/`. If `--extract-text` is supposed to be opt-in, users get unexpected `.txt` files.
**How to avoid:** Add `extract_text: bool` to `PipelineConfig`. Only write `.txt` to `final/` when enabled. Internal text is still extracted for quality analysis but not persisted.

### Pitfall 4: --json and Rich Progress Conflict
**What goes wrong:** If `--json` is set but Rich progress bars still print to stderr/stdout, JSON output is corrupted.
**How to avoid:** When `--json` is set, use `NullCallback` instead of `RichCallback`. Only print the final JSON to stdout.

### Pitfall 5: Async Job Memory Leak
**What goes wrong:** `_jobs` dict grows unboundedly as jobs complete but are never cleaned up.
**How to avoid:** Add TTL-based cleanup (e.g., remove completed jobs after 1 hour) or a max job limit.

## Code Examples

### JSON Metadata File Content Structure
```json
{
  "filename": "document.pdf",
  "success": true,
  "engine": "tesseract",
  "quality_score": 0.92,
  "page_count": 15,
  "pages": [
    {
      "page_number": 0,
      "status": "good",
      "quality_score": 0.95,
      "engine": "tesseract",
      "flagged": false
    },
    {
      "page_number": 1,
      "status": "good",
      "quality_score": 0.88,
      "engine": "surya",
      "flagged": false
    }
  ],
  "time_seconds": 12.3,
  "phase_timings": {
    "extract_text": 0.5,
    "analyze_quality": 0.2,
    "tesseract": 8.1
  }
}
```

### MCP Context Progress Reporting
```python
# Source: Context7 /modelcontextprotocol/python-sdk
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

@mcp.tool()
async def ocr(input_path: str, ctx: Context[ServerSession, None], ...) -> dict:
    await ctx.info(f"Starting OCR: {input_path}")
    await ctx.report_progress(progress=0.0, total=1.0, message="Initializing")
    # ... run pipeline ...
    await ctx.report_progress(progress=1.0, total=1.0, message="Complete")
    return result_dict
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| MCP tasks via experimental API | Still experimental in python-sdk | 2025+ | Use simple in-process job store for stdio transport |
| Sync MCP tools | `asyncio.to_thread()` for blocking work | Already implemented | Keep this pattern |

## Open Questions

1. **Should `.txt` files be opt-in or always written?**
   - What we know: Pipeline currently always writes `.txt`. Requirement says `--extract-text` "triggers" it.
   - Recommendation: Make `.txt` output opt-in via flag. Pipeline still extracts text internally for quality analysis.

2. **Job cleanup strategy for MCP async**
   - What we know: In-process dict has no persistence or TTL.
   - Recommendation: Simple TTL (1 hour) with lazy cleanup on each `ocr_status()` call. Acceptable for single-user desktop tool.

3. **Progress bridging for synchronous `ocr()` MCP tool**
   - What we know: Pipeline runs in thread, MCP progress is async. Bridging is complex.
   - Recommendation: Add `ctx` parameter to `ocr()` tool, report progress at phase boundaries (before/after Tesseract, before/after Surya) rather than per-file. Accept coarse-grained progress for sync tool; fine-grained progress via `ocr_status()` for async.

## Sources

### Primary (HIGH confidence)
- Context7 `/modelcontextprotocol/python-sdk` - FastMCP Context, progress reporting, experimental tasks API
- Codebase analysis: `types.py`, `pipeline.py`, `mcp_server.py`, `cli.py`, `callbacks.py`, `postprocess.py`

### Secondary (MEDIUM confidence)
- MCP experimental tasks documentation (from Context7) - tasks require Streamable HTTP transport, not suitable for stdio

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all stdlib + existing deps
- Architecture: HIGH - based on direct codebase analysis, clear extension points
- Pitfalls: HIGH - identified from reading actual code paths

**Research date:** 2026-02-02
**Valid until:** 2026-03-04
