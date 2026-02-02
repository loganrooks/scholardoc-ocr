# Domain Pitfalls

**Domain:** Hybrid OCR pipeline rearchitecture (Python CLI to library + CLI)
**Researched:** 2026-01-28 (v1), 2026-02-02 (v2 additions)
**Confidence:** HIGH (grounded in actual codebase bugs and domain experience)

---

## V1 Pitfalls (Pipeline Foundation)

### Critical Pitfalls

### Pitfall 1: Surya Output Discarded After Processing

**What goes wrong:** The pipeline runs Surya OCR on bad pages, extracts text, maps it back to files -- then never writes the improved text back to the output files or replaces pages in the output PDFs.

**Why it happens:** The Phase 2 code was written incrementally. The mapping logic was built but the final write step was never implemented.

**Consequences:** Surya models load (30-60s), GPU processes all pages, then the results vanish.

**Prevention:**
- Every processing step must have an assertion or test that its output persists
- Write an integration test: process a known-bad PDF, verify the final output contains Surya text
- Design the pipeline with explicit "write-back" as a named step

**Detection:** Compare the text file content before and after Phase 2.

### Pitfall 2: PyMuPDF File Handle Leaks on Exceptions

**What goes wrong:** `PDFProcessor` opens fitz documents but only closes them in the happy path. Exceptions leak C-level file descriptors.

**Prevention:** Use context managers (`with fitz.open(path) as doc:`). The current code already uses `_open_pdf` context manager -- ensure all new code follows this pattern.

**Detection:** `lsof -p <pid> | grep -c pdf` during processing.

### Pitfall 3: CPU Oversubscription in Nested Parallelism

**What goes wrong:** ProcessPoolExecutor spawns N processes, each running ocrmypdf which uses internal threading. Two levels of parallelism without coordinated resource budgets.

**Prevention:** Treat total CPU budget as shared resource. Cap `jobs_per_file` when running multiple files.

### Pitfall 4: Fragile Index-Based Page Mapping Between Phases

**What goes wrong:** Phase 2 maps Surya results back using positional indexing. If any page is skipped, all subsequent pages map wrong.

**Prevention:** Use explicit page identifiers (file + page number), not positional indices. Assert length matches before mapping.

### Moderate Pitfalls

### Pitfall 5: ML Model Lifecycle Mismanagement

**Prevention:** Models loaded exactly once per pipeline run. Use model manager pattern. Never import Surya at module level.

### Pitfall 6: CLI-to-Library Extraction Breaks Error Handling

**Prevention:** Define exception hierarchy. Library layer must never import Rich or call sys.exit().

### Pitfall 7: Testing OCR Pipelines Without Deterministic Fixtures

**Prevention:** Synthetic test PDFs with known text. Mock OCR for logic tests. Real OCR tests marked slow.

### Pitfall 8: Temp File Cleanup Failures Filling Disk

**Prevention:** Use `tempfile.TemporaryDirectory` for intermediates. Cleanup in `finally` blocks.

### Pitfall 9: Marker/Surya API Instability

**Prevention:** Pin version strictly. Adapter module with version detection.

### Minor Pitfalls

### Pitfall 10: ProcessPoolExecutor Serialization Constraints

**Prevention:** Keep worker functions at module level. All arguments must be picklable.

### Pitfall 11: Quality Threshold as Single Global Number

**Prevention:** Per-page-type thresholds or minimum word count filters.

---

## V2 Pitfalls (Post-Processing, Logging, MCP Async, Robustness)

Pitfalls specific to adding text post-processing, structured logging, async MCP job handling, environment validation, and temp/work directory management to the existing scholardoc-ocr pipeline.

### Critical Pitfalls

### Pitfall 12: Dehyphenation Destroys Intentional Hyphens

**What goes wrong:** A naive dehyphenation pass (rejoin word-hyphen-newline) destroys compound words that happen to fall at line breaks. In academic texts this is especially dangerous: German compound words (e.g., "Selbst-bewusstsein"), French philosophical terms with hyphens (e.g., "peut-etre"), and hyphenated author names (e.g., "Merleau-Ponty") get mangled.

**Why it happens:** Tesseract emits soft hyphens (U+00AD) for line-break hyphens, but real hyphens are U+002D. Developers treat all end-of-line hyphens the same. Additionally, OCR engines inconsistently use soft vs hard hyphens -- Tesseract uses soft hyphens, but Surya/Marker outputs plain hyphens for everything.

**Consequences:** "Merleau-Ponty" becomes "MerleauPonty". "Selbst-bewusstsein" becomes "Selbstbewusstsein" (which happens to be valid German, so this is a silent semantic change). Scholarly citations become unparseable.

**Prevention:**
- Distinguish U+00AD (soft hyphen, always a line-break artifact) from U+002D (hard hyphen, may be intentional)
- For hard hyphens at line breaks, check if the rejoined word exists in a dictionary before removing the hyphen
- Maintain a whitelist of known hyphenated terms (author names, compound philosophical terms)
- Make dehyphenation language-aware: German compounds rejoin differently than English
- Never dehyphenate inside citation contexts (parenthetical references, footnote markers)

**Detection:** Grep output for known hyphenated terms that should survive post-processing. Unit test with "Merleau-Ponty" at a line break.

**Phase:** Text post-processing phase. Must be designed before implementation.

### Pitfall 13: Unicode Normalization Inconsistency Across OCR Engines

**What goes wrong:** Tesseract and Surya produce different Unicode normalization forms. Tesseract may output "e" + combining acute (NFD) while Surya outputs precomposed "e-acute" (NFC). When the pipeline merges text from both engines (good pages from Tesseract, bad pages from Surya), the same character has different byte representations within one document. This breaks search, comparison, and downstream NLP.

**Why it happens:** Each OCR engine makes independent Unicode choices. The pipeline merges their outputs without normalization. Ligatures add another dimension: Tesseract may output "fi" as two characters while Surya outputs the "fi" ligature (U+FB01).

**Consequences:** Text search fails ("cafe" won't match "cafe" with combining accent). Diff tools show phantom changes. Quality analysis regex patterns may not match. French terms like "etre" with circumflex get inconsistent treatment.

**Prevention:**
- Apply `unicodedata.normalize('NFC', text)` as the first step of all post-processing, before any other transforms
- Decompose ligatures (fi, fl, ff, ffi, ffl) to their component characters -- academic text search expects this
- Add a normalization step at the boundary where Tesseract and Surya text merge (in `run_pipeline`, where page texts are joined)
- Test with a document that has both Tesseract and Surya pages, verify consistent normalization

**Detection:** `len(text.encode('utf-8'))` before and after NFC normalization -- if different, you have mixed forms.

**Phase:** Must be the very first post-processing step. Implement before dehyphenation or any other text transform.

### Pitfall 14: Logging from ProcessPoolExecutor Workers Silently Lost

**What goes wrong:** The current `_tesseract_worker` function uses `logging.getLogger(__name__)` but worker processes inherit a copy of the parent's logging configuration at fork time. With `spawn` start method (default on macOS), workers get NO logging configuration at all -- all log messages are silently dropped. The existing code already has this bug: worker process logs in `_tesseract_worker` go nowhere.

**Why it happens:** Python's `ProcessPoolExecutor` with `spawn` creates fresh interpreter processes. The `logging.basicConfig()` call in the main process doesn't carry over. Developers test on Linux with `fork` (which copies config) and deploy on macOS with `spawn` (which doesn't).

**Consequences:** When Tesseract fails in a worker, the error is caught and returned as a `FileResult.error` string, but the detailed log context (stack traces, intermediate states) is lost. Debugging production issues becomes guesswork.

**Prevention:**
- Use `QueueHandler` in workers sending to a `multiprocessing.Manager().Queue()`, with `QueueListener` in the main process dispatching to real handlers
- Configure logging inside each worker function, not relying on inherited state
- CRITICAL: Do not use `multiprocessing.Queue` directly with pools -- use `Manager().Queue()` which returns proxy objects safe for pool workers
- Avoid the infinite loop trap: ensure the QueueHandler's logger does not propagate to a parent that also has a QueueHandler
- Test logging on macOS (spawn) specifically, not just Linux (fork)

**Detection:** Run the pipeline on macOS, check if worker-level log messages appear. If only main-process messages show, logging is broken.

**Phase:** Structured logging phase. Must be implemented before adding more complex pipeline stages that need debugging.

### Pitfall 15: FastMCP Server Crash on Client Timeout During OCR

**What goes wrong:** The current MCP server runs OCR via `asyncio.to_thread(run_pipeline, config)`. OCR can take 5-30 minutes for large documents. When the MCP client (Claude Desktop) times out waiting, FastMCP's server can crash entirely rather than gracefully cancelling. This is a known FastMCP issue with `streamable-http` transport.

**Why it happens:** The MCP protocol has timeout semantics. When the client disconnects, the server-side `to_thread` call continues running (threads cannot be cancelled in Python). FastMCP does not gracefully handle the disconnect, leading to unhandled exceptions in the event loop.

**Consequences:** Server process dies. Any other pending requests are lost. The OCR work already done is wasted. Temp files from the interrupted run are not cleaned up.

**Prevention:**
- Use FastMCP's `task=True` protocol-native background tasks (available since v2.14) instead of raw `asyncio.to_thread`. This requires making the tool function async and using `TaskConfig` for execution mode
- IMPORTANT: `task=True` only works with async functions -- the current `ocr` tool is already async, but it delegates to sync `run_pipeline` via `to_thread`. The task wrapper must be at the outer async level
- Set `request_timeout` on the FastMCP constructor (e.g., `request_timeout=600` for 10 minutes)
- Send progress notifications during processing to keep the connection alive and prevent client-side timeouts
- Implement graceful shutdown: catch cancellation, clean up temp files, return partial results if available

**Detection:** Start OCR on a large document, kill the Claude Desktop connection mid-processing, check if the server process survives.

**Phase:** MCP async phase. Requires FastMCP >= 2.14.

### Moderate Pitfalls

### Pitfall 16: Post-Processing Corrupts Footnote References

**What goes wrong:** Academic PDFs have superscript footnote numbers that OCR engines extract as inline numbers. Post-processing that "cleans up" text by removing isolated numbers or reformatting whitespace destroys footnote references. A line like "Heidegger argues1 that..." becomes "Heidegger argues that..." or "Heidegger argues 1 that...".

**Why it happens:** Post-processing rules written for "normal" prose don't account for academic text conventions. Footnote markers appear as isolated digits, which look like OCR artifacts.

**Prevention:**
- Never remove isolated numbers unless they match a specific artifact pattern
- Preserve superscript markers by detecting the pattern: word immediately followed by 1-3 digits with no space
- Make post-processing rules configurable and conservative by default
- Test with academic texts that have heavy footnoting

**Phase:** Text post-processing. Design rules with academic texts specifically in mind.

### Pitfall 17: Line Break Detection Varies by OCR Engine

**What goes wrong:** Tesseract uses `\n` for line breaks within paragraphs and `\n\n` for paragraph breaks. Surya/Marker outputs markdown with different conventions. When merging text from both engines, paragraph detection breaks -- some paragraphs get merged, others get split.

**Why it happens:** The pipeline currently joins page texts with `\n\n` (line 161 of pipeline.py) without normalizing line break conventions per engine.

**Prevention:**
- Normalize line breaks as a post-processing step, per-engine, before merging
- Define a canonical internal format (e.g., single `\n` for soft breaks, `\n\n` for paragraphs)
- Apply paragraph detection heuristics: lines ending without period + next line starting lowercase = same paragraph

**Phase:** Text post-processing, after Unicode normalization.

### Pitfall 18: QueueHandler Propagation Infinite Loop

**What goes wrong:** When setting up `QueueHandler` for multiprocess logging, if the root logger has both a QueueHandler (for sending to the listener) and normal handlers, and `propagate=True` on child loggers, log records loop: QueueHandler puts the record in the queue, QueueListener dispatches it back to the root logger, which puts it back in the queue.

**Why it happens:** The Python logging cookbook warns about this but the pattern is easy to get wrong. The current code uses `logging.basicConfig()` in `mcp_server.py:main()` which configures the root logger -- adding a QueueHandler to root creates the loop.

**Prevention:**
- QueueListener must dispatch to handlers on a SEPARATE logger (not root), or handlers must be removed from root before adding QueueHandler
- Set `respect_handler_level=True` on QueueListener
- In worker processes: configure ONLY a QueueHandler on root, no other handlers
- In main process: QueueListener dispatches to file/stream handlers, QueueHandler is NOT on the same logger tree

**Detection:** Log output grows exponentially. CPU spins on logging. Easy to catch in testing if you watch log volume.

**Phase:** Structured logging phase.

### Pitfall 19: Environment Validation That Blocks Startup

**What goes wrong:** Over-eager environment validation checks every possible dependency at startup (Tesseract version, Surya model availability, GPU presence, disk space). This makes the CLI take 10+ seconds to start, or fails entirely when optional components are missing. Users who only want Tesseract mode get errors about missing Surya models.

**Why it happens:** Developers add validation for every issue they've debugged, creating a growing startup tax.

**Prevention:**
- Validate eagerly for REQUIRED components only (Python version, Tesseract binary existence)
- Validate lazily for OPTIONAL components (Surya models: check only when `--force-surya` or quality threshold triggers Phase 2)
- Cache validation results (don't re-check Tesseract version every run)
- Separate "can I start?" validation from "can I do this specific operation?" validation
- Never validate network/model downloads at startup -- defer to first use

**Detection:** Time `ocr --help` -- if it takes more than 1 second, startup validation is too heavy.

**Phase:** Environment validation phase. Design the validation tiers before implementing.

### Pitfall 20: Work Directory Collision Between Concurrent Runs

**What goes wrong:** The current code creates work directories at `output_dir/work/{stem}` (line 66 of pipeline.py). If two pipeline runs process the same file concurrently (e.g., MCP server handling two requests), they write to the same work directory. Intermediate files overwrite each other, producing corrupt output.

**Why it happens:** The work directory path is deterministic based on input filename, with no per-run isolation.

**Prevention:**
- Include a unique run ID (UUID or timestamp) in work directory paths: `output_dir/work/{run_id}/{stem}`
- Use `tempfile.mkdtemp()` for work directories instead of deterministic paths
- Clean up work directories in a `finally` block, or use `tempfile.TemporaryDirectory` as a context manager
- For the MCP server specifically: each `ocr()` call must have isolated temp space since concurrent requests are expected

**Detection:** Launch two OCR requests for the same file simultaneously via MCP, check for corrupt output.

**Phase:** Temp/work directory management. Must be done before MCP concurrent request support.

### Minor Pitfalls

### Pitfall 21: Post-Processing Destroys Greek Transliterations

**What goes wrong:** The quality analyzer already whitelists Greek transliterations ("aletheia", "phronesis", etc.) but post-processing rules like "remove non-English words" or "fix common OCR substitutions" can undo this. For example, a spell-check pass might "correct" "ousia" to "ousla" or flag "eudaimonia" as garbled.

**Prevention:**
- Share the whitelist between quality analysis and post-processing
- Post-processing should never modify words that pass quality analysis validation
- Test with a passage containing dense Greek/German philosophical terminology

**Phase:** Text post-processing. Reuse existing whitelist from `quality.py`.

### Pitfall 22: MCP File Logging Bypass

**What goes wrong:** The current MCP server has a `_log()` function (line 14-19) that bypasses Python's logging framework by writing directly to a file. This was a debugging workaround. If structured logging is added via QueueHandler, these direct-write logs won't go through the new system, creating two parallel logging paths that are hard to correlate.

**Prevention:**
- Remove the `_log()` bypass when implementing structured logging
- Route all MCP server logging through the standard `logging` module
- Ensure the MCP server's `main()` logging configuration is compatible with the new QueueHandler setup

**Phase:** Structured logging phase. Clean up during migration.

### Pitfall 23: Soft Hyphen vs Hard Hyphen Confusion in Text Search

**What goes wrong:** Tesseract outputs soft hyphens (U+00AD) for line-break hyphens. These are invisible in most text editors but present in the byte stream. Users searching the output text for "phenom-enology" won't find it because the soft hyphen is a different character than the search hyphen.

**Prevention:**
- Strip all soft hyphens (U+00AD) and rejoin the surrounding word fragments as a post-processing step
- This is safe because soft hyphens are ALWAYS line-break artifacts, never intentional content
- Do this BEFORE dehyphenation logic (which handles hard hyphens)

**Phase:** Text post-processing. First pass before dehyphenation.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Library API design | CLI concerns leak into library | Define exception hierarchy first |
| Pipeline restructure | Surya results not written back | Integration test verifying output changes |
| Pipeline restructure | Page mapping corruption | Explicit IDs, not positional indices |
| Text post-processing | Dehyphenation destroys compound words (#12) | Soft/hard hyphen distinction + dictionary lookup |
| Text post-processing | Unicode normalization inconsistency (#13) | NFC normalize at engine boundary |
| Text post-processing | Footnote references lost (#16) | Conservative rules, academic-text-aware |
| Text post-processing | Greek/German terms mangled (#21) | Share quality.py whitelist with post-processor |
| Structured logging | Worker logs silently lost (#14) | QueueHandler + Manager().Queue() pattern |
| Structured logging | Infinite loop via propagation (#18) | Separate listener logger from QueueHandler logger |
| Structured logging | MCP _log() bypass (#22) | Remove bypass, route through logging module |
| MCP async | Server crash on client timeout (#15) | FastMCP task=True + progress notifications |
| MCP async | Concurrent run collisions (#20) | UUID-based work directories |
| Environment validation | Startup blocked by optional checks (#19) | Eager for required, lazy for optional |
| Temp directory management | Work dir collision (#20) | Per-run isolation with tempfile |

## Sources

- Direct analysis of current codebase: `pipeline.py`, `processor.py`, `quality.py`, `mcp_server.py` (HIGH confidence)
- [Tesseract soft hyphen behavior](https://github.com/tesseract-ocr/tesseract/issues/2161) (HIGH confidence)
- [Python multiprocessing logging patterns](https://signoz.io/guides/how-should-i-log-while-using-multiprocessing-in-python/) (MEDIUM confidence)
- [Python logging cookbook on QueueHandler](https://docs.python.org/3/library/multiprocessing.html) (HIGH confidence)
- [FastMCP v2.14 background tasks](https://github.com/jlowin/fastmcp/releases/tag/v2.14.0) (HIGH confidence)
- [FastMCP server crash on client timeout](https://github.com/jlowin/fastmcp/issues/823) (HIGH confidence)
- [FastMCP sync tool concurrency issues](https://github.com/jlowin/fastmcp/issues/864) (MEDIUM confidence)
- [MCP timeout handling guide](https://mcpcat.io/guides/fixing-mcp-error-32001-request-timeout/) (MEDIUM confidence)
- [concurrent-log-handler deprecation](https://pypi.org/project/concurrent-log-handler/) (MEDIUM confidence)
