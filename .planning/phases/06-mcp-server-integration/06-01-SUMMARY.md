# Phase 6 Plan 1: MCP Server Module Summary

**One-liner:** FastMCP server exposing OCR pipeline as Claude Desktop tool with page_range, extract_text, and output_name support via stdio transport.

## Completed Tasks

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Add MCP optional dependency and entry point | 1ed0018 | pyproject.toml |
| 2 | Create mcp_server.py with ocr tool | 91fbcdb | src/scholardoc_ocr/mcp_server.py |

## What Was Built

- **MCP server module** (`mcp_server.py`): Single `ocr` tool registered with FastMCP, callable from Claude Desktop via stdio transport
- **Tool parameters**: input_path, quality_threshold, force_surya, max_workers, extract_text, page_range, output_name
- **Lazy imports**: Pipeline and PyMuPDF imported inside tool function to avoid loading ML models at server startup
- **Non-blocking execution**: Pipeline runs via `asyncio.to_thread(run_pipeline, config)`
- **Page range extraction**: PyMuPDF extracts specified pages to temp file before OCR, cleans up after
- **Text extraction**: Writes .txt file alongside output PDF, returns path only (no text in response)
- **Output renaming**: Renames output PDF and associated .txt file after processing
- **Error handling**: All exceptions caught and returned as `{"error": str}` dict

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Lazy imports inside tool function | Consistent with existing pattern (04-01); avoids loading torch/surya at import time |
| page_range creates temp file in source dir | Keeps temp files near source for easy cleanup; avoids cross-filesystem issues |
| extract_text writes .txt not returns text | Prevents huge MCP responses; Claude can read the file if needed |

## Deviations from Plan

None - plan executed exactly as written.

## Metrics

- **Duration:** ~2.5 min
- **Completed:** 2026-02-02
- **Tasks:** 2/2
