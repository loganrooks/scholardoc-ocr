---
status: resolved
trigger: "MCP tool returns '.' is no file error from Claude Desktop but works via direct Python"
created: 2026-02-02T00:00:00
updated: 2026-02-02T00:00:00
---

## Current Focus

hypothesis: CONFIRMED - Claude Desktop launches MCP servers with minimal PATH excluding /opt/homebrew/bin
test: Simulated minimal PATH and checked shutil.which('gs') -> None
expecting: gs not found -> confirmed
next_action: Fix applied and verified

## Symptoms

expected: MCP tool processes PDFs via Claude Desktop and returns structured results
actual: Every call returns "'.' is no file" error regardless of input path validity
errors: "'.' is no file" — Ghostscript error
reproduction: Call ocr MCP tool from Claude Desktop with any PDF path
started: Has never worked from Claude Desktop

## Eliminated

## Evidence

- timestamp: 2026-02-02
  checked: Direct Python invocation
  found: asyncio.run(ocr(...)) works perfectly from venv Python
  implication: Code logic is correct; environment difference between MCP and direct invocation

- timestamp: 2026-02-02
  checked: Log file behavior
  found: ~/scholardoc_mcp.log created but empty (0 bytes)
  implication: main() runs (file created by FileHandler) but _log() may not execute or mcp.run() fails before tool is called

- timestamp: 2026-02-02
  checked: gs location
  found: /opt/homebrew/bin/gs (Ghostscript 10.06.0)
  implication: Homebrew path must be on PATH for ocrmypdf to find gs

- timestamp: 2026-02-02
  checked: Simulated minimal PATH (PATH=/usr/bin:/bin:/usr/sbin:/sbin)
  found: shutil.which('gs') returns None, shutil.which('tesseract') returns None
  implication: CONFIRMED - minimal PATH cannot find gs or tesseract

- timestamp: 2026-02-02
  checked: Fix verification with minimal PATH + _ensure_path()
  found: After _ensure_path(), gs resolves to /opt/homebrew/bin/gs
  implication: Fix works correctly

## Resolution

root_cause: Claude Desktop launches MCP servers with a minimal PATH (/usr/bin:/bin:/usr/sbin:/sbin) that does not include /opt/homebrew/bin. When ocrmypdf calls Ghostscript (gs) via subprocess, gs is not found on PATH. Ghostscript then receives '.' as an argument it cannot resolve, producing the "'.' is no file" error.
fix: Added _ensure_path() function to mcp_server.py that prepends /opt/homebrew/bin, /opt/homebrew/sbin, and /usr/local/bin to PATH at module import time. This ensures all subprocesses (including ProcessPoolExecutor workers) inherit the correct PATH.
verification: Simulated minimal PATH environment, imported module, confirmed gs and tesseract resolve correctly. Syntax check passed.
files_changed:
  - src/scholardoc_ocr/mcp_server.py
