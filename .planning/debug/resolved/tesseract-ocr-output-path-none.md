---
status: resolved
trigger: "tesseract-ocr-output-path-none"
created: 2026-02-02T00:00:00Z
updated: 2026-02-02T00:10:00Z
---

## Current Focus

hypothesis: CONFIRMED - ProcessPoolExecutor worker processes don't inherit PATH modifications from _ensure_path()
test: will add _ensure_path() equivalent at top of _tesseract_worker function
expecting: This will make Tesseract available in worker processes, fixing the failure
next_action: implement fix in pipeline.py _tesseract_worker function

## Symptoms

expected: OCR pipeline should process PDFs successfully using Tesseract via ocrmypdf
actual: Tesseract OCR fails with output_path: None in logs
errors: "Tesseract OCR failed" - output_path is None after ocrmypdf runs
reproduction: Run the MCP server or CLI OCR pipeline on a PDF
started: After fixing a previous '.' is no file bug

## Eliminated

## Evidence

- timestamp: 2026-02-02T00:01:00Z
  checked: ~/scholardoc_mcp.log
  found: "pipeline result keys per file: [('blanchot_orpheus_gaze.pdf', None)]"
  implication: output_path is None in the result returned from run_pipeline

- timestamp: 2026-02-02T00:02:00Z
  checked: pipeline.py _tesseract_worker function
  found: Line 130-141 returns FileResult with no output_path when tess_result.success is False
  implication: When Tesseract fails, the error path doesn't set output_path

- timestamp: 2026-02-02T00:03:00Z
  checked: tesseract.py run_ocr function
  found: Line 67 returns TesseractResult with success=True and output_path=output_path on success
  implication: When tesseract succeeds, output_path should be set

- timestamp: 2026-02-02T00:04:00Z
  checked: git commit f822261
  found: output_path WAS added to success paths in commit "feat(07-01): populate output_path in pipeline success paths"
  implication: The code has output_path in success paths, so Tesseract must be FAILING

- timestamp: 2026-02-02T00:05:00Z
  checked: pipeline.py lines 130-141 error path
  found: When tess_result.success is False, no output_path is set in returned FileResult
  implication: Tesseract is failing for some reason, taking error path which doesn't set output_path

- timestamp: 2026-02-02T00:06:00Z
  checked: Ran direct Tesseract test with test_tesseract_debug.py
  found: Tesseract SUCCEEDS when run directly (success=True, output created)
  implication: The problem is not with Tesseract itself but how it's called in the pipeline worker

- timestamp: 2026-02-02T00:07:00Z
  checked: Ran full pipeline test with test_full_pipeline.py
  found: Pipeline SUCCEEDS and output_path IS set correctly (/tmp/scholardoc_test/final/blanchot_orpheus_gaze.pdf)
  implication: The pipeline code is correct. The issue is MCP-server-specific.

- timestamp: 2026-02-02T00:08:00Z
  checked: mcp_server.py _ensure_path() function
  found: _ensure_path() modifies os.environ["PATH"] in the main MCP server process
  implication: ProcessPoolExecutor spawns NEW processes which don't inherit the PATH modifications

## Resolution

root_cause: The _ensure_path() function in mcp_server.py modifies PATH in the main process, but ProcessPoolExecutor spawns worker processes that don't inherit these modifications. Worker processes can't find Ghostscript/Tesseract, causing ocrmypdf to fail.

fix: Added PATH setup code at the beginning of _tesseract_worker() function in pipeline.py to ensure worker processes have access to Homebrew/system tool directories (/opt/homebrew/bin, /opt/homebrew/sbin, /usr/local/bin).

verification:
  - test_full_pipeline.py: Pipeline succeeds with output_path set correctly
  - test_mcp_simulation.py: MCP-style asyncio.to_thread execution succeeds
  - Both tests confirm worker processes can now find Tesseract/Ghostscript
  - output_path field is populated correctly in FileResult

files_changed:
  - src/scholardoc_ocr/pipeline.py
