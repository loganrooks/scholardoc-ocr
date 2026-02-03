---
phase: quick
plan: 002
type: execute
wave: 1
depends_on: []
files_modified:
  - src/scholardoc_ocr/mcp_server.py
autonomous: true

must_haves:
  truths:
    - "Tool descriptions guide Claude to use real local paths, not fictional upload paths"
    - "Tool descriptions recommend ocr_async for non-trivial jobs to avoid timeout"
    - "Tracebacks in logs are truncated to avoid bloated log files"
    - "Log file rotates when it exceeds 10MB"
  artifacts:
    - path: "src/scholardoc_ocr/mcp_server.py"
      provides: "Updated tool descriptions and robust logging"
      contains: "logging.handlers.RotatingFileHandler"
---

<objective>
Fix MCP tool usability and logging issues: 1) Update tool descriptions to guide Claude toward real local filesystem paths and recommend ocr_async for large jobs, 2) Truncate tracebacks in logs, 3) Add log rotation.

Purpose: Prevent common Claude Desktop failures (fictional paths, timeouts) and stop log file bloat.
Output: Improved MCP server with better tool descriptions and robust logging.
</objective>

<execution_context>
@./.claude/get-shit-done/workflows/execute-plan.md
@./.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/scholardoc_ocr/mcp_server.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Improve tool descriptions for Claude guidance</name>
  <files>src/scholardoc_ocr/mcp_server.py</files>
  <action>
Update the docstrings for all three tools to guide Claude toward correct usage:

**ocr() docstring** (lines 198-217):
- Add a CRITICAL note at the top: Files must exist on the LOCAL filesystem. Paths like `/mnt/user-data/uploads/...`, `/sessions/...`, or `/tmp/claude/...` are invalid. Ask the user for the actual file location on their machine (e.g., `~/Downloads/paper.pdf`).
- Emphasize that for files over ~50 pages or jobs expected to take 5+ minutes, use ocr_async() instead to avoid Claude Desktop's tool timeout.
- Keep existing parameter docs.

**ocr_async() docstring** (lines 110-122):
- Add the same CRITICAL note about local filesystem paths.
- Emphasize this is the PREFERRED tool for: files over 50 pages, directories with multiple PDFs, or any job that may take 5+ minutes.
- Note that it returns immediately with a job_id; use ocr_status() to poll.

**ocr_status() docstring** (lines 163-170):
- Add a note that polling every 10-30 seconds is reasonable for progress updates.
- Mention that jobs expire after 1 hour.
  </action>
  <verify>
    - `grep -c "LOCAL filesystem" src/scholardoc_ocr/mcp_server.py` returns 2 (one for each input tool)
    - `grep -c "ocr_async" src/scholardoc_ocr/mcp_server.py` shows references in ocr() docstring
  </verify>
  <done>Tool docstrings guide Claude to use real local paths and prefer ocr_async for non-trivial jobs.</done>
</task>

<task type="auto">
  <name>Task 2: Add log rotation and truncate tracebacks</name>
  <files>src/scholardoc_ocr/mcp_server.py</files>
  <action>
1. Replace the simple `_log()` function with a proper RotatingFileHandler setup:
   - Import `logging.handlers` at top
   - Create a module-level logger: `_file_logger = logging.getLogger("scholardoc_mcp_file")`
   - Configure it with RotatingFileHandler:
     - maxBytes=10*1024*1024 (10MB)
     - backupCount=3 (keep 3 rotated files)
     - File: `~/scholardoc_mcp.log`
   - Update `_log()` to use `_file_logger.info(msg)`

2. In the exception handler (line 361-363), truncate the traceback:
   - Keep only the last 3 frames of the traceback (most relevant)
   - Format as: `"EXCEPTION: {e}\n{truncated_traceback}"`
   - Use `traceback.format_exc().split('\n')` and take last ~15 lines (3 frames * ~5 lines each)

3. Similarly update the `_run_job()` exception handler (line 97-99) to log truncated tracebacks.
  </action>
  <verify>
    - `grep "RotatingFileHandler" src/scholardoc_ocr/mcp_server.py` finds the handler
    - `grep "maxBytes" src/scholardoc_ocr/mcp_server.py` shows 10MB limit
    - `ruff check src/scholardoc_ocr/mcp_server.py` passes
  </verify>
  <done>Log file rotates at 10MB with 3 backups, tracebacks are truncated to last 3 frames.</done>
</task>

</tasks>

<verification>
- `ruff check src/scholardoc_ocr/mcp_server.py` passes
- `pytest` passes (no functional changes to pipeline)
- Tool descriptions contain path guidance and async recommendations
- Logging uses RotatingFileHandler with 10MB limit
</verification>

<success_criteria>
- Claude reading tool descriptions will know to ask for real local paths
- Claude will prefer ocr_async for large jobs
- Log files will never grow beyond ~40MB (10MB * 4 files max)
- Tracebacks are truncated to prevent log bloat
</success_criteria>

<output>
After completion, create `.planning/quick/002-fix-mcp-tool-issues/002-SUMMARY.md`
</output>
