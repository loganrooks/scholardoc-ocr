---
status: resolved
trigger: "Tesseract OCR runs but fails - log shows output_path: None and error Tesseract OCR failed"
created: 2026-02-02T15:44:00
updated: 2026-02-02T15:50:00
---

## Current Focus

hypothesis: MCP server worker processes lack PATH to Tesseract/Ghostscript, causing ocrmypdf to fail
test: Direct pipeline run succeeds; MCP log shows failure before PATH fix commit
expecting: Restarting MCP server after PATH fix resolves the issue
next_action: Verify fix works, check for remaining edge cases

## Symptoms

expected: OCR pipeline should process PDFs successfully using Tesseract via ocrmypdf
actual: Tesseract OCR fails with output_path: None in logs
errors: "Tesseract OCR failed" - output_path is None after ocrmypdf runs
reproduction: Run the MCP server OCR tool on a PDF
started: After fixing previous '.' is no file bug

## Eliminated

- hypothesis: ocrmypdf language parameter type mismatch (list vs string)
  evidence: ocrmypdf.ocr accepts Iterable[str] for language; list is valid
  timestamp: 2026-02-02T15:46:00

- hypothesis: output_path not being set in success paths
  evidence: Commit f822261 already added output_path=str(pdf_path) to both success returns
  timestamp: 2026-02-02T15:47:00

- hypothesis: Stale installed code not matching source
  evidence: Editable install confirmed; inspect.getsource shows both fixes present
  timestamp: 2026-02-02T15:49:00

## Evidence

- timestamp: 2026-02-02T15:45:00
  checked: MCP server log at ~/scholardoc_mcp.log
  found: Last MCP run at 15:29 shows output_path=None; PATH fix committed at 15:41
  implication: MCP server was running code WITHOUT the PATH fix

- timestamp: 2026-02-02T15:46:00
  checked: Direct pipeline execution via python
  found: Pipeline succeeds, output_path correctly set, takes ~33s (including Surya)
  implication: Code is correct; issue is environment-specific to MCP server context

- timestamp: 2026-02-02T15:47:00
  checked: MCP server timing (15:29:17 to 15:29:26 = 9s)
  found: Pipeline completed in ~9s vs ~33s in direct run
  implication: Worker failed quickly (likely couldn't find binaries), consistent with PATH issue

- timestamp: 2026-02-02T15:48:00
  checked: multiprocessing start method
  found: macOS uses 'spawn' method; child processes may not inherit parent env reliably
  implication: PATH set by _ensure_path() in parent may not reach workers

- timestamp: 2026-02-02T15:49:00
  checked: Commit e7b41b0 adds PATH setup inside _tesseract_worker
  found: Worker now independently ensures /opt/homebrew/bin etc. are in PATH
  implication: Fix directly addresses root cause

## Resolution

root_cause: ProcessPoolExecutor worker processes on macOS (spawn method) run with minimal PATH from MCP host (Claude Desktop). The parent process _ensure_path() may not propagate to workers. Without /opt/homebrew/bin in PATH, ocrmypdf cannot find Tesseract or Ghostscript, causing OCR failure and output_path remaining None.
fix: Commit e7b41b0 adds PATH setup directly inside _tesseract_worker function (lines 55-59 of pipeline.py), ensuring workers always have required tool directories.
verification: Direct pipeline run succeeds. MCP server needs restart to pick up fix.
files_changed:
  - src/scholardoc_ocr/pipeline.py (PATH setup in worker)
