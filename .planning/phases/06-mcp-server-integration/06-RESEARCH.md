# Phase 6: MCP Server Integration - Research

**Researched:** 2026-02-01
**Domain:** Model Context Protocol (MCP) server for Python
**Confidence:** HIGH

## Summary

The MCP Python SDK provides `FastMCP`, a decorator-based framework for exposing Python functions as MCP tools. Creating an MCP server for scholardoc-ocr is straightforward: define a single async tool function that wraps `run_pipeline()`, return structured results, and register the server in Claude Desktop's JSON config.

The existing library API (`run_pipeline(PipelineConfig) -> BatchResult`) with its `to_dict()` serialization is already well-suited for MCP tool output. The FastMCP framework handles stdio transport, argument parsing, and structured output automatically.

**Primary recommendation:** Use `mcp[cli]` package with `FastMCP` to create a single `src/scholardoc_ocr/mcp_server.py` module exposing one `ocr` tool that wraps `run_pipeline()`.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp[cli]` | latest (1.x+) | MCP Python SDK with FastMCP | Official Anthropic SDK, HIGH reputation, 296 code snippets on Context7 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pydantic` | (transitive via mcp) | Structured output schemas | Defining tool return types for structured content |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| FastMCP decorator API | Low-level `Server` class | More control but much more boilerplate; FastMCP is the recommended approach |

**Installation:**
```bash
pip install "mcp[cli]"
```

Add to `pyproject.toml` as optional dependency:
```toml
[project.optional-dependencies]
mcp = ["mcp[cli]"]
```

## Architecture Patterns

### Recommended Project Structure
```
src/scholardoc_ocr/
    mcp_server.py      # NEW — FastMCP server, single file
    pipeline.py         # UNCHANGED — run_pipeline()
    types.py            # UNCHANGED — BatchResult, PipelineConfig
    ...
```

### Pattern 1: FastMCP Tool with Structured Output
**What:** Decorate an async function with `@mcp.tool()`, return a dict or Pydantic model. FastMCP auto-generates the tool schema from type hints and docstring.
**When to use:** Always for this phase.
**Example:**
```python
# Source: Context7 /modelcontextprotocol/python-sdk
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("scholardoc-ocr")

@mcp.tool()
async def ocr(input_dir: str, quality_threshold: float = 0.85, ...) -> dict:
    """Run OCR pipeline on PDF files."""
    config = PipelineConfig(input_dir=Path(input_dir), ...)
    result = run_pipeline(config)
    return result.to_dict()
```

### Pattern 2: Progress Reporting via Context
**What:** Inject `ctx: Context` parameter to report progress during long-running OCR.
**When to use:** OCR can take minutes; progress updates keep the client informed.
**Example:**
```python
# Source: Context7 /modelcontextprotocol/python-sdk
from mcp.server.fastmcp import Context

@mcp.tool()
async def ocr(input_dir: str, ctx: Context, ...) -> dict:
    await ctx.info("Starting OCR pipeline")
    # ... run pipeline ...
    await ctx.report_progress(progress=0.5, total=1.0, message="Tesseract complete")
```

### Pattern 3: Entry Point for Claude Desktop
**What:** Add a script entry point so Claude Desktop can launch via `uvx` or `python -m`.
**Example in pyproject.toml:**
```toml
[project.scripts]
scholardoc-ocr-mcp = "scholardoc_ocr.mcp_server:main"
```

**Claude Desktop config (`claude_desktop_config.json`):**
```json
{
  "mcpServers": {
    "scholardoc-ocr": {
      "command": "path/to/python",
      "args": ["-m", "scholardoc_ocr.mcp_server"]
    }
  }
}
```

### Anti-Patterns to Avoid
- **Modifying pipeline.py for MCP:** The MCP server should wrap the existing API, not change it. Success criterion #3 says "no changes to existing library code."
- **Blocking the event loop:** `run_pipeline()` is CPU-bound and synchronous. Must run it in a thread executor (`asyncio.to_thread()`) to avoid blocking the MCP server's async event loop.
- **Returning raw text content:** Use `to_dict()` for structured results, not raw text dumps.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP protocol handling | Custom stdio JSON-RPC | `mcp` SDK's `FastMCP` | Protocol is complex, SDK handles it |
| Tool schema generation | Manual JSON Schema | FastMCP type-hint inference | Automatic from Python type annotations |
| Structured output serialization | Custom JSON formatting | `BatchResult.to_dict()` + FastMCP | Already built in types.py |

**Key insight:** The entire MCP server is ~30-50 lines of code because FastMCP does the heavy lifting and `run_pipeline()` + `BatchResult.to_dict()` already exist.

## Common Pitfalls

### Pitfall 1: Blocking the Async Event Loop
**What goes wrong:** `run_pipeline()` uses `ProcessPoolExecutor` and is synchronous. Calling it directly in an async tool blocks the MCP server.
**Why it happens:** FastMCP tools are async, but the pipeline is sync.
**How to avoid:** Use `asyncio.to_thread(run_pipeline, config)` to run in a thread.
**Warning signs:** Server becomes unresponsive during OCR processing.

### Pitfall 2: Forgetting stdio Transport
**What goes wrong:** Claude Desktop uses stdio transport. Using HTTP transport won't work.
**Why it happens:** FastMCP examples show both `mcp.run()` (stdio, default) and `mcp.run(transport="streamable-http")`.
**How to avoid:** Use `mcp.run()` with no transport argument (defaults to stdio) or explicitly `mcp.run(transport="stdio")`.
**Warning signs:** Claude Desktop can't connect to the server.

### Pitfall 3: Path Handling
**What goes wrong:** Claude Desktop sends string paths from user messages. These may be relative, use `~`, or not exist.
**Why it happens:** User types natural language paths.
**How to avoid:** Expand `~`, resolve to absolute, validate existence before calling pipeline.
**Warning signs:** Pipeline fails with FileNotFoundError.

### Pitfall 4: Heavy Dependencies at Import Time
**What goes wrong:** Importing `pipeline.py` transitively imports Surya/Marker which loads ML models.
**Why it happens:** Module-level imports in pipeline.py.
**How to avoid:** The pipeline already uses lazy imports (`from . import surya` inside `run_pipeline()`). Just ensure mcp_server.py doesn't eagerly import heavy modules.
**Warning signs:** MCP server takes 30+ seconds to start.

## Code Examples

### Complete MCP Server Module
```python
# src/scholardoc_ocr/mcp_server.py
"""MCP server exposing scholardoc-ocr as a tool for Claude Desktop."""

import asyncio
from pathlib import Path

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("scholardoc-ocr")


@mcp.tool()
async def ocr(
    input_dir: str,
    quality_threshold: float = 0.85,
    force_surya: bool = False,
    max_workers: int = 4,
) -> dict:
    """Run OCR on PDF files in a directory.

    Processes scanned academic PDFs using Tesseract, falling back to Surya
    for pages below the quality threshold.

    Args:
        input_dir: Path to directory containing PDF files.
        quality_threshold: Minimum quality score (0-1) before Surya fallback.
        force_surya: Force Surya OCR on all pages.
        max_workers: Maximum parallel Tesseract workers.

    Returns:
        Structured results with per-file and per-page quality scores.
    """
    from .pipeline import PipelineConfig, run_pipeline

    input_path = Path(input_dir).expanduser().resolve()
    if not input_path.is_dir():
        return {"error": f"Directory not found: {input_dir}"}

    config = PipelineConfig(
        input_dir=input_path,
        output_dir=input_path / "scholardoc_ocr",
        quality_threshold=quality_threshold,
        force_surya=force_surya,
        max_workers=max_workers,
    )

    result = await asyncio.to_thread(run_pipeline, config)
    return result.to_dict()


def main():
    """Entry point for MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Low-level `Server` class | `FastMCP` decorator API | MCP SDK 1.0+ | 90% less boilerplate |
| Text-only tool output | Structured output (Pydantic/dict) | 2025-06-18 spec | Tools can return typed JSON |

## Open Questions

1. **Progress callback integration**
   - What we know: FastMCP supports `ctx.report_progress()`. The pipeline has a `PipelineCallback` protocol.
   - What's unclear: Whether to wire the pipeline callback to MCP progress (adds complexity) or just report start/end.
   - Recommendation: Start simple (no progress bridging). The tool returns when done. Add progress bridging in v2 if needed.

2. **Output directory convention**
   - What we know: Pipeline requires an output_dir. MCP tool needs a sensible default.
   - What's unclear: Best default for MCP context (user may not specify).
   - Recommendation: Default to `{input_dir}/scholardoc_ocr/` matching CLI behavior.

## Sources

### Primary (HIGH confidence)
- Context7 `/modelcontextprotocol/python-sdk` - FastMCP setup, tools, structured output, stdio transport, progress reporting, Claude Desktop config
- Project codebase: `pipeline.py`, `types.py`, `pyproject.toml` - existing API surface

### Secondary (MEDIUM confidence)
- None needed; Context7 docs were comprehensive

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official MCP SDK, well-documented on Context7
- Architecture: HIGH - Pattern is straightforward wrapper, verified with SDK docs
- Pitfalls: HIGH - Async/sync bridge and stdio transport are well-documented concerns

**Research date:** 2026-02-01
**Valid until:** 2026-03-01 (MCP SDK is stable)
