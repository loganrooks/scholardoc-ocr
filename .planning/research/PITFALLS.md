# Domain Pitfalls

**Domain:** Hybrid OCR pipeline rearchitecture (Python CLI to library + CLI)
**Researched:** 2026-01-28 (v1), 2026-02-02 (v2 additions), 2026-02-03 (v3 MPS/performance), 2026-02-17 (v4 diagnostic intelligence)
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

---

## V3 Pitfalls (PyTorch/MPS Performance Optimization)

Pitfalls specific to adding PyTorch/MPS performance optimizations, batching improvements, model caching, and benchmarking to the existing scholardoc-ocr pipeline on Apple Silicon.

### Critical Pitfalls

### Pitfall 24: ProcessPoolExecutor with Fork Corrupts MPS/CUDA State

**What goes wrong:** The current pipeline uses `ProcessPoolExecutor` for Tesseract parallelization. If PyTorch/MPS is initialized in the main process before forking (e.g., by importing Surya at module level or checking `torch.backends.mps.is_available()`), child processes inherit corrupted GPU state. This causes silent failures, tensor zeroing, or deadlocks in worker processes.

**Why it happens:** On macOS, Python 3.8+ defaults to `spawn` (safe), but explicit `fork` usage or Linux deployment triggers the "poison fork" problem. MPS and CUDA runtimes are not fork-safe -- they maintain internal state that becomes invalid after fork. The current code correctly avoids importing Surya in worker functions, but any accidental PyTorch initialization in main before spawning workers will break.

**Consequences:**
- Tensors silently set to zero in worker processes
- Deadlocks during GPU operations
- "MPS backend out of memory" errors that don't reflect actual memory usage
- Intermittent failures that only occur in production, not testing

**Prevention:**
- NEVER initialize PyTorch/MPS before `ProcessPoolExecutor` workers are spawned
- Use explicit `spawn` context: `ProcessPoolExecutor(max_workers=N, mp_context=multiprocessing.get_context('spawn'))`
- Move ALL model loading to after the Tesseract phase completes (current architecture already does this correctly in `run_pipeline`)
- Add defensive check: `assert not torch.backends.mps.is_initialized()` before creating the pool
- If MPS detection is needed early, use `torch.backends.mps.is_built()` (safe) not `is_available()` (may initialize)
- Consider moving Surya to a subprocess rather than in-process to fully isolate GPU state

**Detection:** Run the pipeline with `PYTORCH_DEBUG=1` to get early warnings about fork issues. Check for "RuntimeError: Cannot re-initialize CUDA in forked subprocess" or similar MPS errors.

**Phase:** This is a constraint on the EXISTING architecture. Must be verified before any MPS optimization work begins.

### Pitfall 25: Benchmarking Without GPU Synchronization Shows Wrong Times

**What goes wrong:** Developers time MPS operations with simple `time.time()` wrappers and get misleadingly fast results. GPU operations are asynchronous -- the Python call returns immediately while the GPU is still computing. Without `torch.mps.synchronize()`, benchmarks show CPU dispatch time, not actual computation time.

**Why it happens:** CUDA developers learn to call `torch.cuda.synchronize()`, but MPS is newer and the pattern is less known. Quick benchmarks during development appear to show the code is already fast, masking real performance issues.

**Consequences:**
- "Optimizations" that show 10x speedup in benchmarks but no change in production
- Inability to identify actual bottlenecks
- False confidence that MPS is working when it's actually falling back to CPU
- Regression detection completely broken

**Prevention:**
- Always call `torch.mps.synchronize()` before reading timing results for MPS operations
- Use PyTorch's built-in `torch.utils.benchmark.Timer` which handles synchronization automatically
- For more precise timing, use MPS events:
  ```python
  start_event = torch.mps.event.Event(enable_timing=True)
  end_event = torch.mps.event.Event(enable_timing=True)
  start_event.record()
  # ... operation ...
  end_event.record()
  torch.mps.synchronize()
  elapsed_ms = start_event.elapsed_time(end_event)
  ```
- Include warmup iterations (5-10) before timed runs -- first runs include JIT compilation and cache population
- Run multiple iterations (20+) and report median, not mean

**Detection:** If a benchmark shows an operation taking <1ms that you know involves loading images and running neural networks, synchronization is missing. Compare wall-clock time of full pipeline run vs sum of benchmarked components.

**Phase:** Must establish correct benchmarking methodology BEFORE any optimization work. All performance claims need verified methodology.

### Pitfall 26: MPS TableRecEncoderDecoderModel Falls Back to CPU Silently

**What goes wrong:** Marker/Surya's table recognition model (`TableRecEncoderDecoderModel`) is not compatible with MPS and silently falls back to CPU. The warning message appears once in logs but is easy to miss. Developers assume MPS is accelerating all models when only some are GPU-accelerated.

**Why it happens:** Marker sets `PYTORCH_ENABLE_MPS_FALLBACK=1` to handle unsupported operations. This is necessary for the library to work at all on MPS, but it silently degrades performance for incompatible models. The fallback is per-operation, not per-model, so a single model might be partially on MPS and partially on CPU.

**Consequences:**
- Table recognition is 10-30x slower than expected on Apple Silicon
- Benchmarks that focus on text OCR miss the table bottleneck
- Users with table-heavy documents see dramatically worse performance than benchmarks suggest
- Memory pressure from CPU tensors can cause OOM even with available GPU memory

**Prevention:**
- Audit which Surya models support MPS by checking for the warning at runtime
- For documents without tables, disable table processing: configure Marker with `disable_table_detection=True`
- Log which device each model is actually running on (not just which device was requested)
- Consider using a different table recognition approach for Apple Silicon
- Profile with `torch.profiler` to see actual device utilization per operation

**Detection:** Run with `PYTORCH_ENABLE_MPS_FALLBACK=0` (crash on unsupported ops) to identify which models fall back. Search logs for "Defaulting to cpu instead".

**Phase:** Device detection and model configuration phase. Must understand which models actually use MPS before optimizing.

### Pitfall 27: MPS Memory Leaks in Long-Running Processes

**What goes wrong:** The MPS backend has known memory leaks, particularly with `clip_grad_norm_`, SDPA (Scaled Dot-Product Attention) in float32, and certain tensor conversion patterns. In a long-running MCP server processing many documents, memory grows unboundedly until the system becomes unresponsive or the process is killed.

**Why it happens:** PyTorch MPS is newer and less battle-tested than CUDA. Memory management bugs exist at the Metal/PyTorch interface layer. The leaks are often small per-operation but compound over thousands of operations in a batch processing scenario.

**Consequences:**
- MCP server memory usage grows from 4GB to 20GB+ over a day of processing
- System swap thrashing makes the entire machine unresponsive
- Process RSS grows even though `torch.mps.current_allocated_memory()` shows stable usage
- No explicit error -- system just gets slower and slower

**Prevention:**
- Call `torch.mps.empty_cache()` between documents (not between pages -- too much overhead)
- Call `gc.collect()` after `empty_cache()` to release Python-side references
- Monitor both `torch.mps.current_allocated_memory()` AND process RSS (via `psutil.Process().memory_info().rss`)
- Set `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.7` to trigger earlier cache cleanup (default allows using all GPU memory)
- Implement a watchdog that restarts the MCP server if memory exceeds a threshold
- Consider processing in subprocess batches to get clean memory state periodically

**Detection:** Run a stress test processing 50+ documents sequentially, monitoring memory after each. If RSS grows linearly, there's a leak.

**Phase:** Model lifecycle management phase. Memory cleanup should be part of the batch processing loop.

### Pitfall 28: Batch Size Tuning Ignores MPS Memory Constraints

**What goes wrong:** Developers copy CUDA batch size recommendations (e.g., `RECOGNITION_BATCH_SIZE=864` from Surya benchmarks) without accounting for MPS memory characteristics. MPS unified memory behaves differently than discrete GPU VRAM -- system becomes unresponsive before OOM errors appear because macOS tries to swap GPU memory.

**Why it happens:** Surya's default batch sizes and documentation target H100 GPUs with 80GB VRAM. Apple Silicon's unified memory (8GB-128GB shared between CPU and GPU) requires different tuning. A batch size that "works" may still cause severe system slowdown.

**Consequences:**
- System beach-balls during OCR with no error message
- Other applications become unresponsive
- OCR completes but takes 10x longer due to memory pressure
- `PYTORCH_MPS_HIGH_WATERMARK_RATIO` warnings in logs (if set)

**Prevention:**
- Start with conservative batch sizes for MPS:
  - 8GB unified memory: `DETECTOR_BATCH_SIZE=32`, `RECOGNITION_BATCH_SIZE=16`
  - 16GB unified memory: `DETECTOR_BATCH_SIZE=64`, `RECOGNITION_BATCH_SIZE=32`
  - 32GB+ unified memory: `DETECTOR_BATCH_SIZE=128`, `RECOGNITION_BATCH_SIZE=64`
- Implement adaptive batch sizing: start low, increase if memory headroom exists
- Monitor `torch.mps.recommended_max_memory()` (if available) or estimate as 75% of total unified memory
- Set `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.5` during development to catch memory issues early
- Test on the smallest supported hardware configuration (M1 8GB) not just development machines

**Detection:** Watch Activity Monitor's "Memory Pressure" graph during OCR. If it goes yellow/red, batch sizes are too large.

**Phase:** Batch size configuration phase. Needs hardware-specific profiles.

### Moderate Pitfalls

### Pitfall 29: Model Loading Time Dwarfs Processing Time for Small Documents

**What goes wrong:** Surya model loading takes 30-60 seconds. For a single-page document, this dominates total time (60s load + 5s process = 65s total). Developers optimize the 5s processing time while ignoring the 60s elephant.

**Why it happens:** Model loading happens once at the start of Phase 2, which is correct for batch processing. But when processing single documents via MCP, each request pays the full loading cost. The current architecture loads models fresh for each pipeline run.

**Consequences:**
- Single-document MCP requests take 60+ seconds even for trivial PDFs
- Users perceive the tool as "slow" despite good per-page throughput
- Batching multiple files into one pipeline run is 10x more efficient, but MCP requests arrive one at a time

**Prevention:**
- Implement model caching in the MCP server: load models once on first request, keep warm for subsequent requests
- Add a model warmup on server startup (optional, configurable)
- Consider model quantization to reduce load time (int8 models load faster)
- For CLI usage, batch multiple files in one command rather than invoking once per file
- Set HuggingFace cache directory explicitly to avoid re-downloads: `HF_HUB_CACHE=~/.cache/huggingface/hub`
- Pre-download models during installation, not first run

**Detection:** Profile Phase 2 with `--debug` timing breakdowns. If `model_load_time > total_processing_time`, this pitfall applies.

**Phase:** Model lifecycle management phase. MCP server needs warm model pool.

### Pitfall 30: MPS Device Bug Causes Incorrect Text Detection

**What goes wrong:** Surya's text detection has a known bug when running on MPS (Apple-side bug) that can cause incorrect bounding box detection. The text recognition works, but detection may miss lines or produce malformed boxes.

**Why it happens:** Apple's Metal Performance Shaders have bugs that PyTorch inherits. The Surya maintainer explicitly warns about this in documentation. The bug is at the Metal framework level, not fixable by PyTorch or Surya.

**Consequences:**
- Entire text regions missed in OCR output
- Garbled results when recognition runs on incorrect bounding boxes
- Inconsistent results between runs (non-deterministic behavior)
- Quality scores may be misleadingly high because missing text isn't counted

**Prevention:**
- For critical accuracy, force CPU for detection: set `DETECTOR_DEVICE=cpu` (if Surya supports per-model device)
- Run detection on CPU, recognition on MPS (detection is less compute-intensive anyway)
- Compare MPS and CPU results on a test corpus before deploying
- If MPS detection is used, validate output quality systematically, not just spot-checking
- Keep this pitfall in mind when debugging "random" OCR failures

**Detection:** Process the same document multiple times with MPS detection. If results vary significantly between runs, the bug is affecting you.

**Phase:** Device selection phase. May need per-model device configuration.

### Pitfall 31: torch.compile() Unusable on MPS

**What goes wrong:** Developers attempt to use `torch.compile()` (PyTorch 2.0+) for optimization, but it has limited support on MPS. The compilation either fails or falls back to eager mode with no speedup, while adding significant compilation overhead.

**Why it happens:** `torch.compile()` backends (Triton, inductor) are designed for CUDA and CPU. MPS support is incomplete. The PyTorch team prioritizes CUDA/CPU, and MPS gets second-class support.

**Consequences:**
- 30+ seconds added to first inference for compilation that doesn't help
- Cryptic error messages or silent fallback to eager mode
- Code that works on CUDA fails on MPS
- False optimization hope -- developers spend time on torch.compile instead of effective optimizations

**Prevention:**
- Do NOT use `torch.compile()` on MPS as of PyTorch 2.10 -- check release notes for future support
- Use eager mode optimizations: proper batch sizing, memory management, avoiding CPU-GPU transfers
- If absolute performance is needed, consider MLX (Apple's native framework) which outperforms PyTorch MPS by 2-3x for some workloads
- Focus optimization effort on reducing batch count (fewer inference calls) rather than per-inference speed

**Detection:** If using `torch.compile()`, check logs for "falling back to eager" or measure actual speedup (likely negative).

**Phase:** Optimization phase. Skip torch.compile for MPS.

### Pitfall 32: Float64 Operations Crash on MPS

**What goes wrong:** MPS does not support float64 (double precision) tensors. Operations that work on CPU or CUDA crash with "Cannot convert a MPS Tensor to float64 dtype" when run on MPS.

**Why it happens:** Metal (Apple's GPU API) doesn't support double precision. PyTorch MPS inherits this limitation. Libraries that default to float64 for numerical stability (common in scientific computing) fail on MPS.

**Consequences:**
- Runtime crashes deep in model inference
- Works on CPU, crashes on MPS -- confusing debugging
- Third-party library code may use float64 internally without documentation
- Marker/Surya may have float64 usage in edge cases

**Prevention:**
- Ensure all model inputs are float32: `tensor.to(dtype=torch.float32)`
- Set default dtype before loading models: `torch.set_default_dtype(torch.float32)`
- If a library requires float64, force CPU device for that operation
- Test on MPS early and often -- don't assume CPU-tested code works on MPS
- Catch `RuntimeError` with "float64" in message and provide helpful error

**Detection:** Set `PYTORCH_ENABLE_MPS_FALLBACK=0` during testing to crash immediately on unsupported operations.

**Phase:** Device compatibility phase. Test all code paths on MPS.

### Pitfall 33: Non-Contiguous Tensor Bug on macOS < 15

**What goes wrong:** PyTorch MPS had a kernel bug where operations like `addcmul_` and `addcdiv_` silently produce wrong results when writing to non-contiguous output tensors. Model weights can freeze during training or produce incorrect inference results.

**Why it happens:** macOS 15 added native support for non-contiguous tensors in Metal. Earlier versions required PyTorch to work around limitations, and some workarounds had bugs. PyTorch 2.4+ has fixes, but only on macOS 15+.

**Consequences:**
- Silent incorrect results (no error, just wrong output)
- Works on some inputs, fails on others depending on tensor memory layout
- Extremely difficult to debug -- appears as "random" quality degradation
- Random tensor operations (`normal_`, `uniform_`) still affected even on macOS 15

**Prevention:**
- Require macOS 15+ for MPS usage (document as system requirement)
- On older macOS, fall back to CPU or warn users about potential issues
- After each model operation, verify output with `.contiguous()` and compare
- Use PyTorch 2.4+ minimum
- Call `.contiguous()` on tensors before in-place operations as defensive measure

**Detection:** Run quality validation tests on macOS 14 vs 15. If results differ, this bug may be present.

**Phase:** Environment validation phase. Check macOS version before enabling MPS.

### Minor Pitfalls

### Pitfall 34: Warmup Iterations Counted in Benchmarks

**What goes wrong:** Benchmark code includes the first few iterations in timing averages. First iterations are slow due to: JIT compilation, cuDNN/MPS autotuning, lazy module initialization, memory allocation. This skews benchmarks to show slower-than-actual performance.

**Why it happens:** Copy-paste benchmark code that doesn't follow PyTorch best practices. Quick timing during development without proper methodology.

**Prevention:**
- Always run 5-10 warmup iterations before starting timing
- Use `torch.utils.benchmark.Timer` which handles warmup automatically
- For autotuning (cuDNN), the first run for each input shape is slow -- warm up with representative inputs
- Don't benchmark immediately after model load -- run a few inferences first

**Phase:** Benchmarking methodology. Establish before any optimization measurement.

### Pitfall 35: Unified Memory Accounting Confusion

**What goes wrong:** Developers check `torch.mps.current_allocated_memory()` and see low usage, but the system is still under memory pressure. They increase batch sizes thinking there's headroom, causing system slowdown.

**Why it happens:** MPS unified memory is shared with the CPU and system. `current_allocated_memory()` shows PyTorch's GPU allocations but not: model weights in CPU memory, system overhead, other applications' memory, memory mapped files. The "available" memory is much less than `total - allocated`.

**Prevention:**
- Monitor system-level memory, not just PyTorch's view: `psutil.virtual_memory().available`
- Keep at least 4GB headroom for system operations on 16GB machines
- Test with other applications running (Safari, VS Code) -- real users don't close everything
- Use Activity Monitor's "Memory Pressure" as the source of truth

**Phase:** Memory management phase. System-level monitoring.

### Pitfall 36: HuggingFace Model Downloads During Processing

**What goes wrong:** First run of Surya triggers model downloads (several GB). This happens during OCR processing, causing: timeout errors, incomplete downloads on network issues, inconsistent timing between first and subsequent runs.

**Why it happens:** HuggingFace Transformers downloads models lazily on first use. In development, models are already cached. In production/new installs, the download happens unexpectedly.

**Prevention:**
- Pre-download models during installation: `python -c "from marker.models import create_model_dict; create_model_dict()"`
- Set `HF_HUB_OFFLINE=1` in production to fail fast if models missing (rather than hanging on download)
- Include model download in installation instructions or setup script
- Cache models in Docker images for containerized deployments
- Set explicit cache location: `HF_HUB_CACHE=/path/to/cache` for reproducibility

**Detection:** Time first run vs second run. If first is 10+ minutes longer, downloads are happening.

**Phase:** Environment setup phase. Pre-download during installation.

---

## V4 Pitfalls (Diagnostic Intelligence and LLM Evaluation)

Pitfalls specific to adding diagnostic instrumentation, image quality analysis, LLM-based evaluation (claude CLI + codex CLI), quality scoring calibration, and smart page selection to the existing scholardoc-ocr pipeline for academic philosophy texts.

### Critical Pitfalls

### Pitfall 37: Image Quality Metrics That Do Not Predict OCR Quality

**What goes wrong:** You compute image quality metrics (Laplacian variance for sharpness, histogram spread for contrast, DPI extraction, noise estimation) and discover they do not correlate with actual OCR errors on your corpus. A page with high sharpness and good contrast still produces garbled OCR because the problem is a faded photocopy, unusual font, or tight line spacing. Conversely, a slightly blurry scan of large clear type produces perfect OCR. You build an entire image diagnostic system that cannot predict which pages need help.

**Why it happens:** Generic image quality metrics were designed for photography, not scanned documents. Research shows only ~0.7 correlation between document image quality prediction algorithms and actual OCR accuracy -- and that is with algorithms specifically designed for documents, not generic sharpness/contrast measures. For scanned academic philosophy texts (which often have: small footnote fonts, Greek characters, German compound words, ligatures, and marginal annotations), the correlation is likely worse. The fundamental problem is that OCR quality depends on the interaction between image properties AND the specific characters/language being recognized, which image-only metrics cannot capture.

**Consequences:**
- Image metrics become "noise that looks like signal" -- they produce numbers, but the numbers do not tell you anything actionable
- Developers spend weeks building image analysis infrastructure that provides zero predictive value for the actual OCR quality decisions
- Image quality "scores" give false confidence -- pages flagged as "poor image quality" may OCR perfectly, while pages flagged as "good image quality" may OCR terribly
- If used to gate image preprocessing, wrong pages get preprocessed (see Pitfall 40)

**Prevention:**
- Measure image metrics AND OCR quality on the same pages, then compute correlation BEFORE building any image-quality-driven logic
- Start with a validation step: run image metrics on 50+ pages where you know the OCR quality, and check if metrics actually predict quality
- If correlation is below 0.6, image metrics are not useful for this corpus -- do not build infrastructure around them
- Use image metrics only for descriptive diagnostics ("this page has DPI X and sharpness Y") not for predictive decisions ("this page will OCR poorly because sharpness is low")
- The actual useful image metrics for OCR are text-specific: character height in pixels (below 20px x-height causes Tesseract problems), stroke thickness, and whether text is binarizable. Generic metrics like "overall sharpness" are not useful

**Warning signs:**
- Image quality scores are uniformly high across your corpus (scanned academic books are generally clean scans)
- Image quality and OCR quality rankings do not align when you spot-check
- You find yourself adding exceptions and special cases to make image metrics "work"

**Detection:** Scatter plot of image quality metric vs. OCR quality score for 50 pages. If R-squared < 0.3, abandon the predictive use of that metric.

**Phase to address:** First diagnostic instrumentation phase. Must validate metric correlation BEFORE building image-quality-driven features.

---

### Pitfall 38: LLM Evaluator Inconsistency Across Runs (Rating Roulette)

**What goes wrong:** You send the same OCR text to Claude or Codex for quality evaluation and get different scores on different runs. A page rated 4/5 on Monday gets rated 2/5 on Tuesday with identical input. Your evaluation results are not reproducible, making it impossible to measure whether quality scoring calibration actually improved or just got lucky.

**Why it happens:** LLM outputs are inherently stochastic. Even with temperature=0, API-level batching, caching, and routing can produce different outputs. Research confirms this is a fundamental problem: "Rating Roulette: Self-Inconsistency in LLM-As-A-Judge" (EMNLP 2025 Findings) documents that even frontier models exhibit significant self-inconsistency in evaluation tasks. For OCR evaluation specifically, the problem is amplified because the differences between "good" and "acceptable" OCR output are subtle -- a few garbled words in 500 -- and LLMs are particularly inconsistent on marginal cases.

**Consequences:**
- Evaluation results are not reproducible: calibration experiments that "improve" scores might just be noise
- You cannot detect regressions because the signal-to-noise ratio of the evaluator is too low
- Multi-run comparisons (before/after quality scoring changes) become meaningless
- Developers lose trust in the evaluation system and stop using it

**Prevention:**
- Run every evaluation 3 times minimum and use the median score, not a single run
- Use binary or 3-point scales, not 5-point or 10-point scales -- research shows LLMs are much more consistent on coarse scales
- Include explicit rubrics with concrete examples in the evaluation prompt: "Score 1 if more than 5% of words are garbled. Score 0 if text is unreadable." NOT "Rate the quality from 1-5"
- Set temperature=0 for all evaluation calls (necessary but not sufficient for consistency)
- Track evaluator consistency as a meta-metric: for a calibration set of 10 pages, run evaluation 5 times each and compute the standard deviation. If stdev > 0.5 on a 5-point scale, the evaluation prompt needs tightening
- Consider structured output (JSON with specific fields) rather than free-form scoring -- constrains the LLM's output space and improves consistency
- Log every LLM evaluation call with the full prompt and response for reproducibility auditing

**Warning signs:**
- "Improvements" that do not reproduce when you re-run the evaluation
- Evaluator scores for the same page fluctuate by more than 1 point on a 5-point scale
- Results change when you re-run without changing anything

**Detection:** Run evaluation on 10 fixed pages, 3 times each. Compute Cohen's kappa of evaluator with itself across runs. If kappa < 0.6, consistency is insufficient for calibration work.

**Phase to address:** LLM evaluation framework phase. Must establish consistency baseline BEFORE using evaluator results for calibration decisions.

---

### Pitfall 39: LLM Evaluator Hallucination When Judging OCR Quality

**What goes wrong:** The LLM evaluator "sees" errors that do not exist, or "corrects" OCR text using its world knowledge rather than evaluating it. Claude reads "Heidegger's concept of Dasein" and reports no errors -- but the actual OCR text was "Heldegger's concept of Dasein" (capital-I-missing-from-"Heidegger"). The LLM auto-corrected while reading. Conversely, the LLM reports that "aletheia" is a garbled word because it does not recognize the Greek philosophical term.

**Why it happens:** LLMs are trained to be helpful, not to be precise character-level validators. They read for meaning, not for orthographic accuracy. When processing OCR text, the LLM's language model "fills in" expected words, making it blind to subtle character-level errors that humans and edit-distance metrics catch. This is documented in OCR evaluation research: "the processes of character recognition and text generation in multimodal LLMs are integrated, making it difficult to evaluate the accuracy of each separately."

**Consequences:**
- Evaluator overestimates OCR quality (most common failure mode) because it auto-corrects errors while reading
- Evaluator flags correct specialized terminology as errors (German philosophy terms, Greek transliterations, French accented words)
- Calibration based on hallucinated evaluations drives quality thresholds in the wrong direction
- The problem is invisible because the evaluator provides confident, articulate justifications for its hallucinated assessment

**Prevention:**
- NEVER ask the LLM "is this text correct?" -- it will auto-correct and say yes
- Instead, ask the LLM to compare OCR output against a reference (the original page image) or to identify specific character-level anomalies: "List every word that contains an unusual character sequence, a missing letter, or a character that does not belong"
- Provide the LLM with the source image alongside the text when possible -- this grounds the evaluation in visual evidence rather than linguistic plausibility
- Include domain vocabulary in the evaluation prompt: "The following terms are correct and should not be flagged as errors: Dasein, aletheia, Selbstbewusstsein, differance..."
- Cross-validate LLM evaluations against mechanical metrics (CER against known-good text, garbled regex scores) -- if LLM says "perfect" but CER is 5%, the LLM is hallucinating
- Use the LLM for semantic-level evaluation ("does this paragraph convey coherent meaning?") and mechanical metrics for character-level evaluation ("what percentage of words are garbled?") -- do not use the LLM for both

**Warning signs:**
- LLM evaluator scores are consistently higher than mechanical quality scores
- LLM evaluator never flags pages that the garbled regex detector flags
- LLM evaluator provides detailed "analysis" that does not reference any specific errors in the text

**Detection:** Take 10 pages where you know there are specific OCR errors (from garbled regex results). Ask the LLM to evaluate them. If it misses more than 30% of known errors, it is hallucinating through them.

**Phase to address:** LLM evaluation framework phase. Design evaluation prompts to resist auto-correction.

---

### Pitfall 40: Image Preprocessing That Helps Some Pages But Hurts Others

**What goes wrong:** You implement image preprocessing (adaptive binarization, deskewing, denoising, contrast enhancement) to improve OCR quality on low-quality pages. Testing on your 4 philosophy PDFs shows improvement on Simondon (photocopied scans) but degradation on Derrida (clean born-digital). You either apply preprocessing globally (hurting clean pages) or build complex per-page logic that is fragile and hard to maintain.

**Why it happens:** There is no universal image preprocessing pipeline for OCR. Research confirms: "Due to the diverse content that can be in an image, there is not a single preprocessing pipeline that can be the most effective for every possible image." Adaptive binarization (Otsu, Sauvola) can destroy thin strokes, light-colored text, or background texture that was not actually noise. Deskewing can introduce artifacts at page margins. Denoising can smooth out small characters (footnotes, Greek diacriticals).

**Consequences:**
- Net-negative impact: preprocessing hurts more pages than it helps
- Quality scoring calibration becomes unreliable because preprocessing introduces a new variable
- Debugging becomes harder: "Is this error from OCR or from preprocessing?"
- Academic texts are particularly vulnerable because they have thin strokes, small fonts, and diacritical marks that preprocessing can destroy

**Prevention:**
- NEVER apply preprocessing globally -- always make it per-page or per-region
- Implement preprocessing as an optional, separable step that can be evaluated independently: run OCR with and without preprocessing on the same page and compare quality scores
- Start with the absolute minimum preprocessing: only operations with proven benefit on your corpus (e.g., DPI upscaling if source is 150 DPI, derotation if pages are visibly skewed)
- CRITICAL: Measure preprocessing impact on your actual corpus before deploying. Run quality analysis on 20+ pages with and without each preprocessing step. If the step does not improve median quality by at least 0.05, do not include it
- Binarization is irreversible -- once applied, the original grayscale information is lost. Never binarize if you are going to feed to Surya/Marker (which can handle color/grayscale input)
- Tesseract has its own internal binarization (Otsu) -- external binarization before Tesseract often does not help and sometimes hurts

**Warning signs:**
- Preprocessing improves scores on some pages but worsens them on others
- You find yourself tuning preprocessing parameters per-book or per-scan-type
- Preprocessing parameters that work for your test corpus fail on new documents

**Detection:** A/B test: run 50 pages through the pipeline with and without preprocessing. If the win/loss ratio is not at least 3:1 (preprocessing helps 3 pages for every 1 it hurts), the preprocessing is not worth deploying.

**Phase to address:** Image analysis/preprocessing phase. Must come AFTER diagnostic metrics are validated, not before.

---

### Pitfall 41: Evaluation Schema That Breaks Comparability Across Runs

**What goes wrong:** You design an evaluation schema (JSON format with scores, criteria, metadata) and iterate on it during development. Version 1 had 3 criteria; version 2 adds 2 more and changes the scoring scale from 3-point to 5-point. You cannot compare evaluation results from Week 1 (v1 schema) with Week 3 (v2 schema) because the schemas are incompatible. All your baseline measurements are invalidated.

**Why it happens:** Evaluation schemas evolve naturally as you discover what matters. But unlike code (where refactoring is reversible), evaluation data collected under an old schema cannot be re-collected without re-running expensive LLM evaluations. Research on ML reproducibility identifies five pillars, and data versioning plus experiment logging are the most frequently missed. Developers version their code but not their evaluation schemas, prompts, or rubrics.

**Consequences:**
- Historical evaluation data becomes useless -- you cannot track quality improvements over time
- "Did we actually improve?" becomes unanswerable because the measurement instrument changed
- Calibration experiments must be restarted from scratch when the schema changes
- Schema changes that seem minor (adding a field, renaming a criterion) break downstream analysis scripts

**Prevention:**
- Version the evaluation schema explicitly: `schema_version: "1.0"` in every evaluation result
- Make schema changes additive only: never remove or rename fields, only add new ones
- If you must change the scoring scale, create a new field rather than modifying the existing one: `quality_v1: 2` (3-point) alongside `quality_v2: 3` (5-point)
- Store the evaluation prompt template alongside the schema version -- the prompt IS part of the schema because changing the prompt changes the results even if the output format stays the same
- Include a `prompt_hash` or `prompt_version` in every evaluation result so you can filter by prompt version
- Define the schema BEFORE running any evaluations, and freeze it for at least one complete calibration cycle before allowing changes
- Use a migration pattern: when schema v2 is introduced, provide a mapping function from v1 results to v2 format (even if lossy)

**Warning signs:**
- You have evaluation results in multiple incompatible formats
- Analysis scripts have special-case handling for "old" vs "new" evaluation results
- Team members are unsure which evaluation results are comparable to which

**Detection:** Can you write a single analysis query that processes all historical evaluation results? If not, your schemas are fragmented.

**Phase to address:** Evaluation schema design phase. Must be the FIRST thing designed, before any evaluation runs.

---

### Pitfall 42: Overfitting Quality Scoring Calibration to a Small Test Corpus

**What goes wrong:** You calibrate quality scoring weights (currently garbled: 0.4, dictionary: 0.3, confidence: 0.3 with threshold 0.85) using LLM evaluation results from 4 philosophy PDFs (~60-100 evaluated pages total). The calibrated weights produce excellent agreement on those 4 books but fail on new documents -- a medieval Latin text, a bilingual French-English edition, or a heavily annotated Nietzsche reader. Your quality scoring is overfit to a tiny, non-representative corpus.

**Why it happens:** With 4 books from 2 authors (Simondon and Derrida), the corpus is heavily biased toward: 20th-century French philosophy, specific publisher typesetting conventions, similar scan quality, similar footnoting styles. Any machine learning practitioner would flag a training set of 4 instances as absurdly small, but the problem is masked because each book has many pages, creating an illusion of sample size. The pages within a single book are NOT independent samples -- they share font, layout, scan quality, and language distribution.

**Consequences:**
- Quality threshold appears well-calibrated (good agreement with LLM evaluator on the 4 training books) but miscalibrates on new books
- Weights that work for French continental philosophy may fail for: analytic philosophy (English, minimal foreign terms), classical texts (heavy Greek/Latin), or anthologies (mixed quality per chapter)
- Users who bring their own documents get worse results than the developer's tests suggest
- The quality scoring system cannot be trusted for the stated use case (academic philosophy broadly)

**Prevention:**
- Treat each BOOK as one sample, not each page. 4 books = 4 samples. This is insufficient for calibration
- Use leave-one-book-out cross-validation: calibrate on 3 books, test on the 4th. Repeat for all 4. Report the variance
- Explicitly partition the corpus into calibration set (used to tune weights) and validation set (never seen during tuning). The validation set MUST include at least one book not used during calibration
- Track calibration performance per-book, not just aggregate. If one book is consistently miscalibrated, the weights are overfit to the others
- When calibrating, weight each book equally rather than weighting each page equally -- otherwise the largest book dominates
- Plan to expand the corpus: add at least 2-3 books from different authors, periods, and languages before calling calibration "done"
- Document the calibration corpus explicitly: which books, which pages, what languages, what conditions. This is the "training data" and its limitations must be transparent
- Use regularization: prefer weights that are close to the current defaults (0.4/0.3/0.3) unless there is strong evidence to change them. Small adjustments are safer than large ones with limited data

**Warning signs:**
- Calibration produces very different weights from the current defaults (large changes from small data = overfitting)
- Leave-one-book-out scores vary by more than 0.1 threshold points
- A new book consistently gets wrong quality predictions

**Detection:** Leave-one-book-out cross-validation. If the optimal threshold varies by more than 0.05 across folds, the calibration is not stable enough to deploy.

**Phase to address:** Quality scoring calibration phase. MUST use cross-validation methodology from the start.

---

### Pitfall 43: Diagnostic Overhead That Slows the Production Pipeline

**What goes wrong:** You add image quality analysis (rendering pages to images, computing Laplacian variance, histogram analysis), per-page diagnostic logging, and LLM evaluation calls to the OCR pipeline. What was a 2-minute pipeline for a 200-page book now takes 15 minutes because: (a) rendering each page to an image for quality analysis takes ~0.5s/page via `fitz.get_pixmap(dpi=300)`, (b) computing numpy metrics on 300-DPI images adds ~0.3s/page, (c) LLM evaluation API calls add seconds per evaluated page.

**Why it happens:** Diagnostic instrumentation is designed to measure, not to be measured. Developers add "one more metric" without profiling the cumulative overhead. PyMuPDF's `get_pixmap()` is known to use significant memory (the pixmap for a 300-DPI A4 page is ~25MB uncompressed) and the memory is not always released promptly. Computing numpy metrics on these large arrays adds CPU overhead. For a 200-page book, this is 200 * (0.5 + 0.3) = 160 seconds of pure diagnostic overhead.

**Consequences:**
- Pipeline runtime doubles or triples for large documents
- Memory usage spikes from rendering full-resolution page images for metrics that may not be useful (see Pitfall 37)
- Users disable diagnostics because they are "too slow," defeating the purpose
- MCP server requests time out because diagnostic overhead pushes processing past the timeout window

**Prevention:**
- Diagnostics MUST be opt-in, not default: `--diagnostics` flag for CLI, `diagnostics=true` parameter for MCP
- Image analysis should use LOW resolution rendering (72-150 DPI, not 300 DPI) for quality metrics -- you are measuring image properties, not doing OCR. A 72-DPI render is 17x smaller than 300-DPI in pixel count
- Cache rendered images: the pipeline already renders pages for confidence extraction (`confidence.py` line 31 uses `dpi=300`). Do not re-render for image quality analysis. Share the pixmap
- Profile the diagnostic overhead budget: diagnostics should add no more than 20% to pipeline runtime. If they add more, something is wrong
- LLM evaluation should NEVER be in the hot path. Run it asynchronously, post-pipeline, or on a sample of pages (the "smart page selection" of 15-25 pages per book)
- Use Pillow's `.resize()` for quick downsample rather than re-rendering at lower DPI if you need both high-res (for OCR) and low-res (for metrics) images
- Release pixmap memory explicitly: `del pixmap` after extracting metrics, and consider processing pages in small batches rather than all at once

**Warning signs:**
- Pipeline takes noticeably longer with diagnostics enabled vs disabled
- `psutil.Process().memory_info().rss` spikes during diagnostic analysis
- The time spent on diagnostics exceeds the time spent on actual OCR

**Detection:** Profile the pipeline with and without diagnostics. If diagnostic overhead exceeds 20% of base pipeline time, optimize before shipping.

**Phase to address:** First diagnostic instrumentation phase. Performance budget must be established upfront.

---

### Critical Pitfall 44: Multi-Evaluator Disagreement Without a Resolution Protocol

**What goes wrong:** You use both Claude (via `claude` CLI) and Codex (GPT-5.3-codex via `codex` CLI) as evaluators. They disagree on 30-40% of pages. Claude rates a page 4/5; Codex rates it 2/5. You have no principled way to resolve disagreements, so you either: (a) average the scores (masks real disagreement), (b) always trust one evaluator (makes the other pointless), or (c) manually adjudicate (does not scale). Your "multi-evaluator" system produces ambiguous results that are harder to act on than a single evaluator.

**Why it happens:** Different LLMs have different biases. Research shows Claude achieves kappa=0.842 on evaluation tasks while GPT-4o achieves kappa=0.853 -- but these are self-consistency measures, not cross-model agreement. Cross-model agreement is typically lower. For OCR evaluation specifically, the models will disagree on: (a) whether specialized terminology is an OCR error, (b) how severely to weight minor formatting issues, (c) whether missing text (blank regions) should tank the score. These are genuine evaluative disagreements, not measurement noise.

**Consequences:**
- Ambiguous results: "Claude says good, Codex says bad" is not actionable
- Averaging scores hides the disagreement pattern -- if Claude consistently scores higher than Codex, the average tracks Claude with dampened sensitivity
- You cannot use disagreement to identify genuinely hard cases (which is the most valuable signal from multi-evaluator setups)
- Time and API cost doubled for marginal benefit

**Prevention:**
- Define a disagreement resolution protocol BEFORE running any evaluations:
  - If both evaluators agree (within 1 point on 5-point scale): use the average
  - If evaluators disagree by 2+ points: flag for manual review AND log the disagreement pattern
  - Track systematic disagreement: does Claude consistently score higher? On what types of content?
- Use evaluators for DIFFERENT purposes rather than the same purpose:
  - Claude: semantic coherence evaluation ("does this paragraph make sense?")
  - Codex: character-level accuracy evaluation ("identify specific OCR errors")
  - This gives complementary signals rather than conflicting scores
- Compute inter-evaluator Cohen's kappa on a calibration set. If kappa < 0.6, the evaluators are too inconsistent to combine meaningfully -- pick one and use the other for spot-checks only
- Use a voting protocol like CLEV: start with both evaluators; if they agree, accept; if they disagree, request a re-evaluation from one of them with additional context (the page image). Majority rules
- Track disagreement as a diagnostic signal: pages where evaluators disagree are pages where quality is genuinely ambiguous -- these are the most interesting pages for calibration

**Warning signs:**
- Evaluators agree less than 70% of the time on binary (good/bad) classification
- One evaluator's scores are consistently 0.5-1.0 points higher than the other's
- You find yourself always choosing one evaluator's answer over the other's

**Detection:** Run both evaluators on 20 calibration pages. Compute Cohen's kappa. If kappa < 0.6, redesign the evaluation protocol before proceeding.

**Phase to address:** LLM evaluation framework phase. Disagreement protocol must be designed before multi-evaluator runs.

---

### Moderate Pitfalls

### Pitfall 45: Ground Truth That Is Not Ground Truth (LLMs as Both Judge and Jury)

**What goes wrong:** You use LLM evaluations as "ground truth" to calibrate quality scoring weights, then validate those weights using more LLM evaluations. The system is circular: the ground truth was generated by the same type of system being validated. If the LLM has a systematic blind spot (e.g., it does not catch subtle character substitutions like l/1 or O/0), the calibrated weights will also be blind to those errors, and the validation will confirm the blind spot.

**Why it happens:** True ground truth for OCR requires human-transcribed reference text, which is expensive and slow. LLM evaluation is fast and cheap. The temptation to treat LLM evaluations as ground truth is strong because they are articulate and confident. But "confident" does not mean "correct" -- LLMs can provide detailed analysis of text quality while missing actual errors (see Pitfall 39).

**Consequences:**
- Quality scoring weights are calibrated to match LLM biases, not actual text quality
- Systematic LLM blind spots become invisible: if the LLM and quality scorer agree that a page is "good," nobody checks whether it actually is
- The evaluation system validates itself -- it cannot detect its own failures
- When a real user reports poor OCR quality on a page the system scored as "good," there is no data to diagnose why

**Prevention:**
- Create a small human-validated ground truth set (even 10-20 pages): manually transcribe or validate OCR output for a diverse set of pages, including known-difficult content (dense Greek, small footnotes, margin annotations)
- Use human ground truth as the FINAL validation layer: LLM evaluations can propose calibration changes, but the changes must be validated against human ground truth before deploying
- Track where LLM evaluations disagree with mechanical metrics (garbled regex, dictionary score, Tesseract confidence). If the LLM says "good" but mechanical metrics say "bad," manually examine those pages -- they reveal LLM blind spots
- Treat LLM evaluations as one signal among several, not as the authoritative judgment. The composite quality score should synthesize LLM evaluation WITH mechanical metrics, not replace them
- If human ground truth is too expensive for the full corpus, create it for a "golden set" of 10 pages that represent the range of difficulty in your corpus. All calibration changes must be validated against this golden set

**Warning signs:**
- LLM evaluations agree with your quality scoring system more than 90% of the time (suspicious -- real quality systems have more false positives/negatives)
- You have no human-validated reference for any page in your corpus
- LLM evaluation results never contradict the existing quality scoring logic

**Detection:** Manually read 5 pages that the system scored as "good" (high quality). If you find OCR errors that neither the quality scorer nor the LLM flagged, you have a circular validation problem.

**Phase to address:** Evaluation framework design. Create human golden set BEFORE calibration.

---

### Pitfall 46: Smart Page Selection That Misses the Hard Cases

**What goes wrong:** You implement "smart page selection" to evaluate only 15-25 pages per book (instead of all pages). The selection algorithm chooses a stratified sample based on quality scores, but it systematically misses the pages that are most informative for calibration: pages near the threshold boundary, pages with unusual content (bibliography, index, chapter title pages, pages with figures), and pages where mechanical metrics and visual quality diverge.

**Why it happens:** Quality score distributions in scanned books are bimodal: most pages are either clearly good or clearly bad. Random or stratified sampling heavily samples from these modes and misses the thin tail of interesting edge cases. The pages near the threshold (the "gray zone" in the current `QualityAnalyzer`, defined as threshold +/- 0.05) are the most important for calibration but are underrepresented in any sample that does not explicitly target them.

**Consequences:**
- Evaluation confirms what you already know (good pages are good, bad pages are bad) and provides no information about the calibration boundary
- Threshold calibration is based on pages far from the threshold, where small changes do not matter
- Special page types (bibliography, index, figure-heavy pages, chapter openings with decorative fonts) are never evaluated because they are rare in any random sample
- Wasted LLM API calls on pages that do not inform calibration

**Prevention:**
- Explicitly oversample the gray zone: 40% of selected pages should be within 0.10 of the current threshold (0.75-0.95 for threshold 0.85)
- Include at least one page from each category: highest quality page, lowest quality page, page near threshold, page with most garbled words, page with lowest Tesseract confidence, first page (title/copyright), last page (bibliography/index), one page from the middle of a chapter
- NEVER select pages purely randomly -- random selection is not efficient for calibration
- Select pages BEFORE evaluation and freeze the selection. Do not adaptively select more pages based on evaluation results (this introduces selection bias)
- Document the selection criteria so the selection can be reproduced or modified in future runs
- For each book, the minimum informative selection is: 3 pages near threshold + 3 pages clearly good + 3 pages clearly bad + 3 edge cases (bibliography, footnote-heavy, figure page) = 12 pages minimum

**Warning signs:**
- All selected pages have similar quality scores (no spread)
- No pages from the gray zone are in the selection
- Selection does not include bibliography, index, or figure pages

**Detection:** Plot the quality score distribution of selected pages vs. all pages. If the selected pages do not span the full range and oversample the boundary, the selection is not informative.

**Phase to address:** Smart page selection design. Must be designed explicitly, not defaulted to random sampling.

---

### Pitfall 47: Evaluation Prompt Sensitivity Invalidates Results

**What goes wrong:** You craft an LLM evaluation prompt and use it for weeks. Then you make a "minor" wording change (reorder the criteria, change "rate" to "evaluate," add one example) and scores shift systematically by 0.3-0.5 points. All your historical evaluation data is now on a different scale. You did not realize the prompt was the calibration instrument, and changing it is like recalibrating a scale mid-experiment.

**Why it happens:** Research documents extensive prompt sensitivity in LLM-as-judge: "prompt template design, including the formulation of rubrics, order of score descriptions, and inclusion of reference answers, has a pronounced effect on both the alignment to humans and consistency." Changes as small as swapping the order of score descriptions (putting "5 = excellent" before vs. after "1 = poor") can shift scores by 0.03-0.2 points depending on the model.

**Consequences:**
- Historical evaluation data invalidated by prompt changes
- Calibration experiments that span multiple prompt versions produce nonsensical results
- Developers unknowingly introduce evaluation drift by "improving" the prompt
- The evaluation system measures prompt version, not OCR quality

**Prevention:**
- Treat the evaluation prompt as versioned code: `prompt_v1.txt`, `prompt_v2.txt`, etc.
- Include `prompt_version` and `prompt_hash` in every evaluation result
- When changing the prompt, re-evaluate the calibration set under both prompts and compute the shift
- Never change the prompt mid-calibration-cycle. Finish the current cycle, then start a new one with the new prompt
- Use the prompt hash (SHA-256 of the prompt text) as the version identifier, not a manually incremented number -- this catches accidental changes
- Test prompt changes on a small calibration set first (10 pages) before applying to full corpus
- Keep a prompt changelog documenting what changed and why

**Warning signs:**
- Evaluation scores shift noticeably after a "minor" prompt update
- Different team members use slightly different prompts
- There is no record of which prompt version generated a particular evaluation result

**Detection:** After any prompt change, re-evaluate 10 calibration pages. If median score shifts by more than 0.2 on a 5-point scale, the change is significant and historical data may not be comparable.

**Phase to address:** LLM evaluation framework phase. Prompt versioning must be built into the evaluation infrastructure from day one.

---

### Pitfall 48: Test Corpus Bias (All Derrida/Simondon = Not Generalizable)

**What goes wrong:** Your test corpus of 4 philosophy PDFs represents two French authors from the same era, likely from similar publishers and scanning sources. Diagnostic instrumentation, quality calibration, and evaluation prompts are tuned to this narrow corpus. When users process Kant in German, Aristotle in Greek translation, or a 19th-century Nietzsche facsimile, the system performs poorly because none of those characteristics were represented in development.

**Why it happens:** The development corpus is the corpus the developer has access to. It is natural to test with what you have. The problem is that the system is not marketed as "OCR for Simondon and Derrida" -- it is marketed as OCR for "academic philosophy texts," which is a vastly broader category.

**Consequences:**
- Quality scoring weights optimized for French philosophical vocabulary may over-flag or under-flag other languages
- The garbled regex patterns in `_GarbledSignal` already have German/Greek/Latin allowlists, but the evaluation prompts may not account for these terms
- Image quality metrics tuned to the scan quality of these 4 books may not generalize
- Evaluation prompts that reference "philosophical terminology" may not handle the specific challenges of other traditions (e.g., Sanskrit transliterations in Indian philosophy, extensive footnoting conventions in analytic philosophy)

**Prevention:**
- Explicitly document what the test corpus covers and does NOT cover:
  - Languages represented: French, English (translations/commentary)
  - Languages NOT represented: German, Greek, Latin, Italian
  - Document types represented: monographs
  - Document types NOT represented: anthologies, journal articles, dissertations, facsimile editions
- When building evaluation prompts, make the domain vocabulary list extensible, not hardcoded. Use the existing allowlists from `quality.py`'s `_GarbledSignal.VALID_TERMS` as input to the evaluation prompt
- Test at least one document from a different tradition/language before shipping. Even one German philosophy text would reveal whether the system generalizes
- Design all scoring and evaluation to be language-parameterized from the start, even if only French/English is tested initially
- Flag the corpus limitation in documentation so users know what to expect

**Warning signs:**
- Evaluation results are suspiciously good (>95% agreement) on the test corpus
- No evaluation results exist for any non-French philosophy text
- German/Greek/Latin terms in the garbled signal allowlist were never tested with the evaluation system

**Detection:** Process one document in a language/tradition not in the test corpus. If quality scores or evaluation results are noticeably worse, corpus bias is confirmed.

**Phase to address:** Test corpus construction phase. Should run in parallel with calibration, not after it.

---

### Minor Pitfalls

### Pitfall 49: PyMuPDF get_pixmap() Memory Pressure in Image Analysis

**What goes wrong:** Image quality analysis renders each page to a Pillow/numpy array via `fitz.get_pixmap(dpi=300)` for metrics computation. For a 200-page A4 book at 300 DPI, each page is ~25MB uncompressed (2480x3508 pixels * 3 channels). Processing all pages sequentially without releasing memory builds up to ~5GB of memory pressure. On the 8GB MPS machines that are the target deployment, this competes with the OCR pipeline for memory.

**Why it happens:** `get_pixmap()` returns a C-level buffer. Python garbage collection may not release it promptly, especially if referenced in numpy arrays. The memory issue is documented in PyMuPDF GitHub discussions. Developers who render a few pages during testing do not see the problem; it only manifests at scale.

**Consequences:**
- Memory pressure causes macOS swap, making the entire system unresponsive
- On 8GB machines, image analysis for a 200-page book may cause OOM or system freeze
- Pipeline appears to "hang" during image analysis because it is swapping, not computing
- Interaction with MPS memory pressure (from model loading) is particularly dangerous

**Prevention:**
- Use lower DPI for image analysis (72-150 DPI, not 300 DPI). For sharpness and contrast metrics, 150 DPI is sufficient. This reduces memory 4x (150 DPI) or 17x (72 DPI)
- Process pages in small batches (10-20 pages) with explicit memory cleanup between batches:
  ```python
  for batch in chunks(pages, 20):
      metrics = [compute_metrics(page) for page in batch]
      del batch  # release C-level pixmap memory
      gc.collect()
  ```
- Do NOT store all page images in memory simultaneously. Compute metrics for one page, store results, release the image
- Reuse the pixmap from `confidence.py`'s `extract_page_confidence()` if both image analysis and confidence extraction are needed for the same page -- do not render the page twice
- Monitor memory during development: `psutil.Process().memory_info().rss` before and after image analysis

**Warning signs:**
- Memory usage exceeds 4GB during image analysis phase
- Activity Monitor shows "Memory Pressure" in yellow/red during diagnostics
- Processing appears to stall on large documents during the image analysis step

**Detection:** Monitor RSS memory during image analysis of a 200-page document. If it grows beyond 2GB, memory management needs optimization.

**Phase to address:** Image analysis implementation. Memory management must be designed, not bolted on.

---

### Pitfall 50: Template/Prompt Versioning That Breaks Reproducibility

**What goes wrong:** Evaluation prompt templates are stored as strings in Python code or as separate text files. They get modified without version tracking. When you later try to reproduce an evaluation result from 2 weeks ago, you cannot determine which prompt version generated it. Changing one word in a prompt can shift scores (see Pitfall 47), but there is no audit trail.

**Why it happens:** Prompts feel like "configuration" not "code." They are not versioned with the same discipline as source files. They live in the codebase but are not covered by tests. Research identifies prompt versioning as a gap in ML reproducibility: "unlike traditional software development, where versioning source code is sufficient to reproduce builds, ML workflows can degrade significantly with changes to... any preprocessing steps."

**Consequences:**
- Cannot reproduce past evaluation results
- Cannot determine if a quality score change is due to a code change, a calibration change, or a prompt change
- Cannot roll back to a known-good prompt version
- Different developers may use different prompt versions without realizing it

**Prevention:**
- Store prompt templates in versioned files (e.g., `src/scholardoc_ocr/evaluation/prompts/quality_v1.txt`) committed to git
- Every evaluation result record includes the prompt file hash
- Prompt changes require a new version file -- never modify in place
- Automated test: evaluation on 3 golden-set pages must produce consistent results with the current prompt version
- Consider a prompt registry: a dictionary mapping version IDs to prompt texts, with the active version stored in configuration

**Warning signs:**
- Prompts are inline strings in evaluation code (easy to accidentally modify)
- No hash or version identifier in evaluation result records
- You cannot answer "which prompt generated this evaluation?"

**Detection:** Search for inline prompt strings in evaluation code. If found, they need to be extracted to versioned files.

**Phase to address:** Evaluation infrastructure phase. Must be built before any evaluation runs.

---

### Pitfall 51: CLI Subprocess Cost for LLM Evaluation

**What goes wrong:** You use `claude` CLI and `codex` CLI as evaluation backends by spawning them as subprocesses. Each evaluation call incurs subprocess startup cost (Python interpreter, CLI argument parsing, authentication) plus API latency. For 25 pages * 2 evaluators * 3 runs (for consistency), that is 150 subprocess invocations, each taking 3-10 seconds = 7-25 minutes of pure evaluation overhead per book.

**Why it happens:** The CLI tools are designed for interactive use, not for programmatic high-throughput evaluation. Each invocation is independent -- no connection pooling, no batch evaluation, no shared authentication context.

**Consequences:**
- Evaluation is prohibitively slow for iterating on calibration
- Developers reduce consistency runs (3 down to 1) or reduce evaluated pages (25 down to 10) to save time, degrading evaluation quality
- Subprocess failures (authentication timeouts, rate limits) interrupt long-running evaluation batches
- Each subprocess creates a new process, consuming memory and potentially triggering rate limits

**Prevention:**
- Batch evaluation calls: format multiple pages into a single prompt where possible (e.g., "Evaluate the following 5 pages" with numbered sections)
- Implement retry logic with exponential backoff for rate limits and timeouts
- Cache evaluation results aggressively: if a page's OCR text has not changed, its evaluation should not change. Hash the input text and skip re-evaluation if the hash matches a cached result
- Consider using the API directly (Anthropic Python SDK, OpenAI Python SDK) instead of CLI subprocesses for programmatic evaluation -- eliminates subprocess overhead entirely
- If CLI must be used (for architectural reasons), implement a job queue that batches evaluations and runs them with controlled concurrency
- Profile the actual overhead: time the CLI startup vs. the API call to understand where time is spent

**Warning signs:**
- Evaluation of one book takes more than 30 minutes
- Rate limit errors appear in logs during evaluation runs
- Developers skip consistency runs "to save time"

**Detection:** Time a single evaluation call. If subprocess startup (non-API time) exceeds 2 seconds, consider API-direct approach instead.

**Phase to address:** LLM evaluation infrastructure phase. API vs CLI decision should be made early.

---

### Pitfall 52: Diagnostic Data That Nobody Reads

**What goes wrong:** You build comprehensive diagnostic output: per-page image quality metrics, signal breakdowns, LLM evaluation transcripts, comparison matrices. The output is a 500-line JSON file per book that nobody knows how to interpret. The diagnostics exist but do not inform any decision, because there is no summarization or actionable guidance layer.

**Why it happens:** Building the instrumentation is the hard engineering work, so it feels like progress. But the gap between "we have data" and "the data tells us what to do" is substantial. Developers build diagnostic infrastructure without designing the consumption interface.

**Consequences:**
- Diagnostic infrastructure has a maintenance cost but zero value
- Quality improvements stall because nobody can interpret the diagnostic output
- The system looks sophisticated (lots of metrics!) but is not actually data-driven

**Prevention:**
- For every metric, define in advance: "What decision does this metric inform?" If there is no answer, do not collect the metric
- Design a summary view FIRST: a one-page report per book with 3-5 key findings and specific recommendations
- Implement alert-level diagnostics: instead of "here are 200 page metrics," produce "3 pages need attention: pages 47, 92, 156 (reasons: ...)"
- The diagnostic output should answer: "What should I do next?" not "What does this data show?"
- Pair every metric with a threshold: "sharpness < X means the scan quality may be causing OCR issues"

**Warning signs:**
- Nobody has looked at the diagnostic output in 2+ weeks
- Diagnostic JSON files are accumulating but are never referenced
- Developers cannot explain what a specific diagnostic metric means for pipeline quality

**Detection:** Ask: "Based on diagnostic output, what specific action should be taken for the last book processed?" If nobody can answer in 30 seconds, the diagnostics need a summarization layer.

**Phase to address:** Diagnostic reporting phase. Design the consumption interface alongside the instrumentation, not after.

---

## Technical Debt Patterns (V4)

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Inline prompt strings in evaluation code | Faster to iterate on prompts | Cannot version prompts, breaks reproducibility | Never -- always use versioned files |
| Single LLM evaluator (skip multi-evaluator) | Simpler, faster, cheaper | Unknown evaluator bias becomes invisible | MVP only -- add second evaluator within 2 sprints |
| 300 DPI rendering for image metrics | Reuse existing pixmap from confidence extraction | 4x memory overhead vs. 150 DPI, potential OOM | Only when reusing existing 300-DPI render, not for dedicated image analysis |
| Averaging disagreeing evaluator scores | Simple aggregation | Masks systematic disagreement, hides evaluator bias | Never -- use disagreement resolution protocol |
| Hardcoded vocabulary in evaluation prompts | Quick to build | Does not generalize beyond test corpus languages | MVP only -- must parametrize before shipping |
| Skipping consistency runs (1 instead of 3) | 3x faster evaluation | Cannot distinguish signal from noise in results | During development iteration, never for calibration |

## Integration Gotchas (V4)

Common mistakes when connecting to external evaluation services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `claude` CLI as evaluator | Spawning one subprocess per page evaluation | Batch multiple pages per prompt; consider API SDK instead |
| `codex` CLI as evaluator | Not handling rate limits | Implement retry with exponential backoff; cache results by input hash |
| PyMuPDF `get_pixmap()` for image analysis | Rendering at 300 DPI for metrics that need 150 DPI | Use lowest DPI sufficient for each metric; share pixmaps between confidence and image analysis |
| Pillow/numpy for image metrics | Loading full-color image for grayscale metrics | Convert to grayscale immediately; release color buffer |
| LLM evaluation output parsing | Expecting consistent free-form text output | Use structured output (JSON mode) or regex extraction with fallback |

## Performance Traps (V4)

Patterns that work during development but break at scale.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Rendering all pages for image analysis | Memory spike, system unresponsive | Process in batches of 20, explicit cleanup | Books with 100+ pages |
| LLM evaluation in the pipeline hot path | Pipeline 10x slower | Move evaluation post-pipeline or async | Any production use |
| Storing full evaluation transcripts per page | Diagnostic files grow to 100MB+ | Store summary scores; full transcript only for flagged pages | Books with 200+ pages |
| Computing all image metrics for every page | 0.5-1.0s overhead per page | Compute only metrics relevant to page type (skip sharpness for born-digital) | Large documents (100+ pages) |
| No evaluation result caching | Re-evaluate unchanged pages on every run | Hash input text; skip if hash matches cached result | Iterative calibration (10+ runs) |

## "Looks Done But Isn't" Checklist (V4)

Things that appear complete but are missing critical pieces.

- [ ] **Image quality metrics:** Often missing correlation validation -- verify that metrics actually predict OCR quality on your corpus (R-squared > 0.3)
- [ ] **LLM evaluation framework:** Often missing consistency measurement -- verify self-agreement (kappa > 0.6) before using for calibration
- [ ] **Multi-evaluator setup:** Often missing disagreement protocol -- verify resolution strategy exists and is documented before running evaluations
- [ ] **Quality scoring calibration:** Often missing cross-validation -- verify leave-one-book-out variance is < 0.05 threshold points
- [ ] **Evaluation schema:** Often missing version tracking -- verify every evaluation result has schema_version and prompt_hash
- [ ] **Smart page selection:** Often missing gray-zone oversampling -- verify at least 40% of selected pages are within 0.10 of threshold
- [ ] **Diagnostic output:** Often missing consumption interface -- verify summary report exists, not just raw metrics
- [ ] **Test corpus:** Often missing diversity -- verify at least one non-French, non-20th-century text is included

## Recovery Strategies (V4)

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Image metrics don't predict OCR quality (#37) | LOW | Stop using predictive metrics. Keep as descriptive only. No code rewrite needed |
| LLM evaluator inconsistency (#38) | MEDIUM | Re-run all evaluations with tightened prompts and 3x consistency. Historical data may be salvageable with wider error bars |
| LLM evaluator hallucination (#39) | MEDIUM | Add mechanical metric cross-validation layer. Re-evaluate suspicious results with source images |
| Preprocessing helps/hurts (#40) | LOW | Make preprocessing opt-in per page. Default to off. No need to remove code |
| Schema comparability broken (#41) | HIGH | Write migration scripts. Re-evaluate calibration set under new schema. Historical data may be unrecoverable |
| Overfitting to small corpus (#42) | MEDIUM | Add 2-3 diverse books to corpus. Re-calibrate. Old weights are still a reasonable starting point |
| Diagnostic overhead too high (#43) | LOW | Make opt-in. Reduce DPI. Process in batches. Straightforward optimization |
| Multi-evaluator disagreement (#44) | MEDIUM | Redesign as complementary (different purposes) rather than redundant (same purpose) |
| Ground truth circularity (#45) | HIGH | Create 10-page human golden set. This is irreplaceable and cannot be shortcut |
| Smart selection misses hard cases (#46) | LOW | Redesign selection criteria. Re-evaluate with better selection. Old data still valid |

## Pitfall-to-Phase Mapping (V4)

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Image metrics don't predict (#37) | Image diagnostics | Correlation > 0.3 validated before building predictive features |
| LLM inconsistency (#38) | Eval framework design | Self-agreement kappa > 0.6 on calibration set |
| LLM hallucination (#39) | Eval prompt engineering | Known-error detection rate > 70% on test pages |
| Preprocessing helps/hurts (#40) | Image preprocessing | A/B test win ratio > 3:1 on 50+ pages |
| Schema breaks comparability (#41) | Eval schema design | Single analysis query works across all historical results |
| Overfitting to corpus (#42) | Calibration methodology | Leave-one-book-out variance < 0.05 |
| Diagnostic overhead (#43) | Diagnostic instrumentation | Overhead < 20% of base pipeline time |
| Multi-evaluator disagreement (#44) | Eval framework design | Inter-evaluator kappa > 0.6 or complementary role assignment |
| Ground truth circularity (#45) | Eval golden set creation | 10+ human-validated pages exist before calibration |
| Smart selection misses cases (#46) | Page selection design | 40%+ of selected pages in gray zone |
| Prompt sensitivity (#47) | Eval infrastructure | Prompt hash in every result; re-eval shift < 0.2 after changes |
| Corpus bias (#48) | Test corpus expansion | At least one non-French text evaluated |
| PyMuPDF memory (#49) | Image analysis impl | RSS < 2GB during 200-page image analysis |
| Template versioning (#50) | Eval infrastructure | All prompts in versioned files; hash in results |
| CLI subprocess cost (#51) | Eval infrastructure | Full evaluation < 30 min per book |
| Diagnostic unused (#52) | Diagnostic reporting | Summary report exists with actionable recommendations |

---

## Phase-Specific Warnings (V3 Additions)

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| MPS optimization | Fork corrupts GPU state (#24) | Verify spawn context, no PyTorch init before pool |
| MPS optimization | TableRec falls back to CPU (#26) | Audit actual device usage per model |
| MPS optimization | Float64 crashes (#32) | Force float32 default |
| MPS optimization | Non-contiguous tensor bug (#33) | Require macOS 15+ |
| Benchmarking | No GPU sync shows wrong times (#25) | Use torch.mps.synchronize() |
| Benchmarking | Warmup counted in averages (#34) | 5-10 warmup iterations before timing |
| Batch size tuning | MPS memory pressure (#28) | Start conservative, adaptive sizing |
| Model caching | Load time dominates small docs (#29) | Warm model pool in MCP server |
| Memory management | MPS leaks in long-running server (#27) | empty_cache() + gc.collect() between docs |
| Memory management | Unified memory accounting (#35) | System-level monitoring, not just PyTorch |
| Environment setup | Downloads during processing (#36) | Pre-download models at install time |
| Device selection | Text detection MPS bug (#30) | Consider CPU for detection, MPS for recognition |

## Phase-Specific Warnings (V4 Additions)

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Image diagnostics | Metrics don't predict OCR quality (#37) | Validate correlation BEFORE building features |
| Image diagnostics | PyMuPDF memory pressure (#49) | Use 150 DPI, batch processing, explicit cleanup |
| Eval framework design | LLM inconsistency (#38) | Binary/3-point scales, 3x runs, measure kappa |
| Eval framework design | Multi-evaluator disagreement (#44) | Complementary roles, not redundant scoring |
| Eval prompt engineering | Hallucination on OCR (#39) | Character-level prompts, domain vocabulary, cross-validate with mechanical metrics |
| Eval prompt engineering | Prompt sensitivity (#47) | Version files, hash in results, test changes on calibration set |
| Eval schema design | Schema breaks comparability (#41) | Version field, additive changes only, migration functions |
| Eval infrastructure | Template versioning (#50) | Versioned files in git, hash in every result |
| Eval infrastructure | CLI subprocess cost (#51) | Batch prompts, consider API SDK, cache results |
| Quality calibration | Overfitting to corpus (#42) | Leave-one-book-out CV, treat books (not pages) as samples |
| Quality calibration | Ground truth circularity (#45) | Human golden set of 10+ pages before calibration |
| Image preprocessing | Preprocessing helps/hurts (#40) | A/B test, opt-in per page, measure before deploying |
| Smart page selection | Misses hard cases (#46) | Oversample gray zone (40%), include edge cases |
| Diagnostic reporting | Nobody reads diagnostics (#52) | Summary view first, answer "what to do next?" |
| Test corpus | Corpus bias (#48) | Document limitations, add one non-French text |
| Pipeline integration | Diagnostic overhead (#43) | Opt-in flag, 20% budget, LLM eval post-pipeline |

---

## Sources

### V1/V2 Sources
- Direct analysis of current codebase: `pipeline.py`, `processor.py`, `quality.py`, `mcp_server.py` (HIGH confidence)
- [Tesseract soft hyphen behavior](https://github.com/tesseract-ocr/tesseract/issues/2161) (HIGH confidence)
- [Python multiprocessing logging patterns](https://signoz.io/guides/how-should-i-log-while-using-multiprocessing-in-python/) (MEDIUM confidence)
- [Python logging cookbook on QueueHandler](https://docs.python.org/3/library/multiprocessing.html) (HIGH confidence)
- [FastMCP v2.14 background tasks](https://github.com/jlowin/fastmcp/releases/tag/v2.14.0) (HIGH confidence)
- [FastMCP server crash on client timeout](https://github.com/jlowin/fastmcp/issues/823) (HIGH confidence)
- [FastMCP sync tool concurrency issues](https://github.com/jlowin/fastmcp/issues/864) (MEDIUM confidence)
- [MCP timeout handling guide](https://mcpcat.io/guides/fixing-mcp-error-32001-request-timeout/) (MEDIUM confidence)
- [concurrent-log-handler deprecation](https://pypi.org/project/concurrent-log-handler/) (MEDIUM confidence)

### V3 Sources (MPS/Performance)
- [PyTorch MPS documentation](https://docs.pytorch.org/docs/stable/mps.html) (HIGH confidence)
- [PyTorch multiprocessing best practices](https://docs.pytorch.org/docs/stable/notes/multiprocessing.html) (HIGH confidence)
- [Elana Simon: The bug that taught me more about PyTorch than years of using it](https://elanapearl.github.io/blog/2025/the-bug-that-taught-me-pytorch/) - Non-contiguous tensor bug deep dive (HIGH confidence)
- [Apple Developer: Accelerated PyTorch training on Mac](https://developer.apple.com/metal/pytorch/) (HIGH confidence)
- [PyTorch MPS memory leak issues](https://github.com/pytorch/pytorch/issues/154329) (MEDIUM confidence)
- [Marker issue #875: 30x slower than Tesseract](https://github.com/datalab-to/marker/issues/875) - Version regression on Apple Silicon (HIGH confidence)
- [Surya issue #207: MacBook M1 performance](https://github.com/VikParuchuri/surya/issues/207) - MPS batch size tuning (MEDIUM confidence)
- [PyTorch Benchmark documentation](https://docs.pytorch.org/tutorials/recipes/recipes/benchmark.html) (HIGH confidence)
- [torch.mps.synchronize() documentation](https://docs.pytorch.org/docs/stable/generated/torch.mps.synchronize.html) (HIGH confidence)
- [MPS SDPA float32 memory leak](https://github.com/pytorch/pytorch/issues/152344) (MEDIUM confidence)
- [PYTORCH_ENABLE_MPS_FALLBACK usage](https://lightning.ai/docs/pytorch/stable/accelerators/mps_basic.html) (HIGH confidence)
- [Marker models.py MPS fallback code](https://github.com/datalab-to/marker/blob/master/marker/models.py) (HIGH confidence)

### V4 Sources (Diagnostic Intelligence and LLM Evaluation)
- [LLM-as-a-judge: complete guide](https://www.evidentlyai.com/llm-guide/llm-as-a-judge) - Known biases (position, verbosity, self-enhancement), mitigation strategies (HIGH confidence)
- [Rating Roulette: Self-Inconsistency in LLM-As-A-Judge](https://aclanthology.org/2025.findings-emnlp.1361.pdf) - EMNLP 2025, documents self-inconsistency in evaluation (HIGH confidence)
- [Survey on LLM-as-a-Judge](https://arxiv.org/abs/2411.15594) - Comprehensive survey of biases and vulnerabilities (HIGH confidence)
- [LLM-as-a-Judge Evaluation - Langfuse](https://langfuse.com/docs/evaluation/evaluation-methods/llm-as-a-judge) - Best practices for prompt design, model selection, calibration (MEDIUM confidence)
- [LLM-as-a-Judge - Patronus AI](https://www.patronus.ai/llm-testing/llm-as-a-judge) - Tutorial on scoring design and consistency (MEDIUM confidence)
- [OlmOCR-Bench Review: Insights and Pitfalls](https://www.llamaindex.ai/blog/olmocr-bench-review-insights-and-pitfalls-on-an-ocr-benchmark) - OCR benchmark pitfalls: data diversity, exact-match brittleness, model bias in ground truth (HIGH confidence)
- [OCR-Quality: Human-Annotated Dataset for OCR Quality Assessment](https://arxiv.org/html/2510.21774) - Need for human-annotated ground truth, uncertainty quantification (MEDIUM confidence)
- [Multi-LLM Thematic Analysis with Dual Reliability Metrics](https://arxiv.org/html/2512.20352) - Cohen's kappa scores for Claude (0.842), GPT-4o (0.853), ensemble strategies (MEDIUM confidence)
- [CLEV: Lightweight Efficient Voting for LLM Evaluation](https://arxiv.org/html/2503.08542) - Two-evaluator + tiebreaker voting protocol (MEDIUM confidence)
- [Reproducibility in ML-based Research](https://onlinelibrary.wiley.com/doi/10.1002/aaai.70002) - Five pillars of ML reproducibility, data versioning gaps (HIGH confidence)
- [Document Image Quality Assessment Survey](https://www.researchgate.net/publication/261126971_Document_Image_Quality_Assessment_A_Brief_Survey) - ~0.7 correlation between quality prediction and OCR accuracy (MEDIUM confidence)
- [Image preprocessing and adaptive thresholding for OCR](https://arxiv.org/abs/2111.14075) - No universal preprocessing pipeline, binarization irreversibility (MEDIUM confidence)
- [PyMuPDF get_pixmap() memory issues](https://github.com/pymupdf/PyMuPDF/discussions/774) - Memory consumption and retention problems (HIGH confidence)
- [PyMuPDF memory retention with get_pixmap()](https://github.com/pymupdf/PyMuPDF/issues/3625) - Memory not released after pixmap creation (HIGH confidence)
- Direct analysis of current codebase: `quality.py` (weights 0.4/0.3/0.3), `confidence.py` (300 DPI rendering), `batch.py` (memory management), `dictionary.py` (domain vocabulary) (HIGH confidence)

---
*Pitfalls research for: scholardoc-ocr diagnostic intelligence and LLM evaluation*
*Researched: 2026-02-17 (V4 additions)*
