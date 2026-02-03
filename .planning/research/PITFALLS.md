# Domain Pitfalls

**Domain:** Hybrid OCR pipeline rearchitecture (Python CLI to library + CLI)
**Researched:** 2026-01-28 (v1), 2026-02-02 (v2 additions), 2026-02-03 (v3 MPS/performance)
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
