# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-03)

**Core value:** Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.
**Current focus:** v2.1 Performance — Surya optimization for Apple Silicon

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-02-03 — Milestone v2.1 started

Progress: v1.0 ✓ | v2.0 ✓ | v2.1 active

## Accumulated Context

### Decisions

See PROJECT.md Key Decisions table for full history.

### Pending Todos

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 001 | Remove brittle PATH hacks, document MCP env config | 2026-02-02 | d04dbdd | [001-remove-brittle-path-hacks](./quick/001-remove-brittle-path-hacks/) |
| 002 | Fix MCP tool issues (path guidance, async preference, log rotation) | 2026-02-03 | a66186a | [002-fix-mcp-tool-issues](./quick/002-fix-mcp-tool-issues/) |

### Blockers/Concerns

- Pre-existing test collection error: test_callbacks.py imports removed `ExtendedResult` from pipeline.py

## Session Continuity

Last session: 2026-02-03
Stopped at: Quick task 002 completed
Resume file: None
