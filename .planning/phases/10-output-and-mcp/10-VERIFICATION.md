---
phase: 10-output-and-mcp
verified: 2026-02-02T22:30:00Z
status: human_needed
score: 4/4 must-haves verified
human_verification:
  - test: "JSON metadata file creation"
    expected: "Run `ocr --extract-text <pdf>`, verify .json file appears in final/ alongside PDF with per-page quality scores, engine info, and stats"
    why_human: "File system verification requires running actual pipeline"
  - test: "Text extraction flag behavior"
    expected: "Run `ocr <pdf>` without flag - no .txt in final/. Run `ocr --extract-text <pdf>` - .txt appears with post-processed text"
    why_human: "Requires comparing filesystem state between two runs"
  - test: "JSON stdout output"
    expected: "Run `ocr --json <pdf>`, verify JSON printed to stdout with no Rich progress bars"
    why_human: "Requires capturing stdout and verifying no Rich output"
  - test: "MCP async job handling"
    expected: "Call ocr_async() via MCP, get job_id immediately. Poll ocr_status(job_id) until status=completed, verify result contains metadata"
    why_human: "Requires MCP client connection and async job execution"
  - test: "MCP progress reporting"
    expected: "Call synchronous ocr() via MCP, observe ctx.info messages for start and completion"
    why_human: "Requires MCP client to observe context messages"
---

# Phase 10: Output and MCP Verification Report

**Phase Goal:** Pipeline results are available in structured formats for programmatic consumers -- JSON metadata alongside PDFs, text extraction via CLI flag, and async MCP handling for long-running jobs.

**Verified:** 2026-02-02T22:30:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A .json metadata file appears alongside each output PDF in final/ containing per-page quality scores, engine provenance, and processing stats | ✓ VERIFIED | Lines 468-476 in pipeline.py write JSON metadata after Phase 2 using FileResult.to_dict() |
| 2 | `ocr --extract-text` writes a .txt file alongside the output PDF; without the flag, no .txt is left in final/ | ✓ VERIFIED | Lines 479-481 in pipeline.py clean up .txt files unless config.extract_text=True; CLI flag at line 245-247 in cli.py |
| 3 | `ocr --json` prints structured JSON to stdout and suppresses Rich progress output | ✓ VERIFIED | Lines 358-383 in cli.py use LoggingCallback instead of RichCallback when --json is set, print batch.to_json() to stdout |
| 4 | MCP `ocr_async()` returns a job ID immediately; `ocr_status(job_id)` reports progress and retrieves results when done | ✓ VERIFIED | Lines 103-159 in mcp_server.py define ocr_async tool with asyncio.create_task; lines 163-184 define ocr_status tool that queries _jobs dict |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/scholardoc_ocr/pipeline.py` | JSON metadata writing after Phase 2, extract_text config control | ✓ VERIFIED | 510 lines, contains json.dumps at line 475, extract_text field at line 46, cleanup at lines 479-481 |
| `src/scholardoc_ocr/cli.py` | --extract-text and --json CLI flags | ✓ VERIFIED | 390 lines, --extract-text flag at line 245, --json flag at line 250, both wired to config and used properly |
| `src/scholardoc_ocr/types.py` | BatchResult.to_json used for --json output | ✓ VERIFIED | 192 lines, to_json at line 190, to_dict at lines 88, 127, 179 |
| `src/scholardoc_ocr/mcp_server.py` | ocr_async tool, ocr_status tool, JobState dataclass, job store with TTL cleanup | ✓ VERIFIED | 383 lines, JobState at line 38, _jobs dict at line 49, ocr_async at line 103, ocr_status at line 163, TTL cleanup at lines 52-62 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| cli.py | PipelineConfig | extract_text flag mapped to config | ✓ WIRED | Line 355 in cli.py: `extract_text=args.extract_text` passed to PipelineConfig |
| pipeline.py | types.py FileResult.to_dict() | JSON metadata file written from to_dict() | ✓ WIRED | Line 472 in pipeline.py calls `file_result.to_dict(include_text=False)`, result written as JSON at line 475 |
| cli.py --json | BatchResult.to_json() | stdout print when --json flag set | ✓ WIRED | Line 383 in cli.py: `print(batch.to_json(include_text=args.extract_text))` when args.json_output is True |
| ocr_async | asyncio.create_task | spawns background task wrapping run_pipeline | ✓ WIRED | Line 156 in mcp_server.py: `asyncio.create_task(_run_job(job, config))` |
| ocr_status | _jobs dict | looks up JobState by job_id | ✓ WIRED | Line 174 in mcp_server.py: `job = _jobs.get(job_id)` |
| ocr tool | ctx.info | reports phase-level progress during synchronous execution | ✓ WIRED | Lines 233, 357 in mcp_server.py call `await ctx.info(...)` for start and completion |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| OUTP-01: JSON metadata file written alongside output PDF | ✓ SATISFIED | Pipeline writes {stem}.json to final/ with quality scores, engine info, stats (lines 468-476) |
| OUTP-02: --extract-text CLI flag triggers post-processing pipeline and writes .txt alongside output | ✓ SATISFIED | CLI flag defined (line 245), wired to config (line 355), pipeline conditionally preserves .txt (lines 479-481) |
| OUTP-03: MCP async job handling — ocr_async returns job ID, ocr_status checks progress | ✓ SATISFIED | ocr_async at line 103, ocr_status at line 163, both tools implemented with JobState tracking |
| OUTP-04: MCP progress events emitted during processing | ✓ SATISFIED | _JobProgressCallback (lines 65-85) updates job.progress dict; synchronous ocr() uses ctx.info (lines 233, 357) |
| OUTP-05: --json CLI flag outputs structured JSON results to stdout | ✓ SATISFIED | Flag at line 250, suppresses Rich output (line 359-361), prints batch.to_json() (line 383) |

### Anti-Patterns Found

No blocking anti-patterns detected:
- No TODO/FIXME/placeholder comments in modified files
- No stub patterns (empty returns are legitimate error handling)
- All functions have substantive implementations
- All exports are used and imported correctly

### Human Verification Required

The following items require human testing to confirm end-to-end behavior:

#### 1. JSON metadata file creation

**Test:** Run `ocr --extract-text ~/test.pdf` on a real PDF
**Expected:** 
- A .json file appears in `~/scholardoc_ocr/final/` alongside the output PDF
- JSON contains keys: `filename`, `success`, `engine`, `pages` (with per-page quality scores), `timings`, `flagged_pages`
- Each page object has `page_number`, `status`, `quality_score`, `engine`, `flagged`

**Why human:** Requires running the full pipeline and inspecting filesystem output

#### 2. Text extraction flag behavior

**Test:** 
1. Run `ocr ~/test.pdf` (without --extract-text)
2. Check if .txt file exists in `~/scholardoc_ocr/final/`
3. Run `ocr --extract-text ~/test.pdf`
4. Verify .txt file appears with post-processed text (dehyphenated, normalized)

**Expected:**
- Without flag: No .txt files in final/
- With flag: .txt file present with clean, post-processed text

**Why human:** Requires comparing filesystem state between two runs and verifying text quality

#### 3. JSON stdout output

**Test:** Run `ocr --json ~/test.pdf` and capture stdout
**Expected:**
- JSON printed to stdout (parseable with `jq`)
- No Rich progress bars visible
- Contains same structure as .json metadata file
- Exit code 0 on success, 1 on error

**Why human:** Requires capturing stdout and verifying absence of Rich terminal codes

#### 4. MCP async job handling

**Test:** Via MCP client:
1. Call `ocr_async(input_path="~/test.pdf")`
2. Capture job_id from response
3. Poll `ocr_status(job_id)` every 5 seconds
4. Verify status transitions: running → completed
5. Verify result contains metadata when complete

**Expected:**
- ocr_async returns immediately (< 1 second) with `{"job_id": "...", "status": "running"}`
- ocr_status initially shows `{"status": "running", "progress": {...}}`
- ocr_status eventually shows `{"status": "completed", "result": {...}}`
- Result structure matches FileResult.to_dict() output

**Why human:** Requires MCP client connection and observing async execution over time

#### 5. MCP progress reporting

**Test:** Via MCP client, call synchronous `ocr(input_path="~/test.pdf")`
**Expected:**
- Context message appears: "Starting OCR: /Users/.../test.pdf"
- Context message appears: "OCR complete: 1 succeeded, 0 failed"
- Messages visible in MCP client logs

**Why human:** Requires MCP client to capture and display context messages

#### 6. Job TTL cleanup

**Test:**
1. Start multiple async jobs via ocr_async
2. Let them complete
3. Wait 61 minutes
4. Call ocr_status on old job_id

**Expected:**
- Old completed jobs return `{"error": "Unknown job: ..."}`
- Memory does not grow indefinitely

**Why human:** Requires long-running test (> 1 hour) to verify TTL expiration

---

## Verification Summary

All automated checks passed. All 4 observable truths are verified in the codebase:

1. ✓ JSON metadata files written alongside PDFs after Phase 2 processing
2. ✓ --extract-text flag controls .txt file persistence, default is cleanup
3. ✓ --json flag prints structured output to stdout, suppresses Rich
4. ✓ MCP async tools (ocr_async, ocr_status) implemented with job tracking

All required artifacts exist and are substantive (1475 total lines across 4 files). All key links are wired correctly. All 5 requirements (OUTP-01 through OUTP-05) are satisfied in the code.

**Human verification needed** to confirm end-to-end behavior: file system outputs, CLI flag interactions, MCP async execution, and progress reporting.

---

_Verified: 2026-02-02T22:30:00Z_
_Verifier: Claude (gsd-verifier)_
