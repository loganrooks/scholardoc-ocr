# Domain Pitfalls

**Domain:** Hybrid OCR pipeline rearchitecture (Python CLI to library + CLI)
**Researched:** 2026-01-28
**Confidence:** HIGH (grounded in actual codebase bugs and domain experience)

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Surya Output Discarded After Processing

**What goes wrong:** The pipeline runs Surya OCR on bad pages, extracts text, maps it back to files -- then never writes the improved text back to the output files or replaces pages in the output PDFs. This is the current bug: `run_surya_batch` returns text, `texts_by_file` is built, but the loop at line 564-567 of pipeline.py only logs "pages enhanced" without actually writing anything.

**Why it happens:** The Phase 2 code was written incrementally. The mapping logic was built but the final write step was never implemented. The code _looks_ complete because it iterates over results and prints status.

**Consequences:** Surya models load (30-60s), GPU processes all pages, then the results vanish. Users see "pages enhanced" in output but get Tesseract-quality text.

**Prevention:**
- Every processing step must have an assertion or test that its output persists: read back the file after writing and verify content changed
- Write an integration test: process a known-bad PDF, verify the final output contains Surya text, not Tesseract text
- Design the pipeline with explicit "write-back" as a named step, not implicit in the processing loop

**Detection:** Compare the text file content before and after Phase 2 -- they will be identical.

**Phase:** Must be fixed in the core pipeline restructure phase, before any other work.

### Pitfall 2: PyMuPDF File Handle Leaks on Exceptions

**What goes wrong:** Every method in `PDFProcessor` opens fitz documents with `self.fitz.open()` but only calls `doc.close()` in the happy path. If any exception occurs between open and close, the file handle leaks. `combine_pages_from_multiple_pdfs` opens a new document per page_spec in a loop -- one exception leaks all previously opened handles.

**Why it happens:** Python developers assume garbage collection handles cleanup. PyMuPDF (fitz) holds C-level file descriptors that may not release promptly, especially on macOS where open file limits are lower.

**Consequences:** Processing 50+ files hits OS file descriptor limits. Silent corruption if a document is modified while another handle holds it open. On macOS, default ulimit is 256 -- easily hit when combining pages from many PDFs.

**Prevention:**
- Use context managers: `with fitz.open(path) as doc:` (PyMuPDF supports this)
- If context managers aren't available for a particular fitz API, use try/finally
- Write a test that processes enough files to exceed default file descriptor limits

**Detection:** `lsof -p <pid> | grep -c pdf` during processing; or set `ulimit -n 64` in tests to catch leaks early.

**Phase:** Fix during processor refactoring, before parallel processing work.

### Pitfall 3: CPU Oversubscription in Nested Parallelism

**What goes wrong:** `ProcessPoolExecutor(max_workers=N)` spawns N processes, each running `ocrmypdf` which itself uses `--jobs=M` threads internally (where M = max_workers // num_files). On a 4-core machine with 4 files, this creates 4 processes x 1 thread = 4 threads (fine). But with 1 file: 1 process x 4 ocrmypdf threads, plus ocrmypdf may spawn its own subprocesses for Ghostscript, unpaper, etc. The real problem: the `jobs_per_file` calculation at line 59 doesn't account for the fact that ocrmypdf already parallelizes across pages internally.

**Why it happens:** Composing two levels of parallelism (Python process pool + ocrmypdf internal threading) without coordinating resource budgets. ocrmypdf's `--jobs` flag controls Tesseract parallelism, but ocrmypdf also runs other tools.

**Consequences:** CPU thrashing, memory pressure (each Tesseract process uses 100-300MB), slower than sequential on memory-constrained systems. With large PDFs and high --jobs, OOM kills are possible.

**Prevention:**
- Treat total CPU budget as a shared resource: `total_cores = os.cpu_count()`; allocate either N workers x 1 job or 1 worker x N jobs, never both high
- Cap `jobs_per_file` at 2 regardless of available cores when running multiple files
- Add memory-aware scheduling: check available RAM before spawning workers
- Make ocrmypdf jobs configurable separately from pipeline workers

**Detection:** Monitor `os.cpu_count()` vs actual concurrent processes during a run. Watch for system memory pressure (psutil).

**Phase:** Address during parallel processing redesign.

### Pitfall 4: Fragile Index-Based Page Mapping Between Phases

**What goes wrong:** Phase 2 maps Surya results back to original files using positional indexing into `all_bad_pages`. If any page fails to extract, is skipped, or if `combine_pages_from_multiple_pdfs` silently drops a page (e.g., page_num >= len(doc)), the indices shift and every subsequent page maps to the wrong file/position.

**Why it happens:** The mapping relies on the assumption that every page in `all_bad_pages` produces exactly one entry in `surya_texts`, in the same order. The batch processing in `run_surya_batch` can produce different numbers of texts (see line 312-317: fallback puts entire markdown as one entry instead of per-page texts).

**Consequences:** Wrong text assigned to wrong pages in wrong files. This is a silent data corruption bug -- output looks plausible but is garbled across documents.

**Prevention:**
- Use explicit page identifiers (file hash + page number) instead of positional indices
- Carry metadata through every processing step, not just at the boundaries
- Assert `len(surya_texts) == len(all_bad_pages)` before mapping, fail loudly if mismatched
- Write a test with 3+ files, each with different bad pages, and verify page-level text assignment

**Detection:** Include source file checksums in output metadata. Spot-check page content against originals.

**Phase:** Must be redesigned in the core pipeline restructure.

## Moderate Pitfalls

Mistakes that cause delays or technical debt.

### Pitfall 5: ML Model Lifecycle Mismanagement

**What goes wrong:** `create_model_dict()` is called in multiple places (`run_surya`, `run_surya_on_pages`, `run_surya_batch`). Each call may load multi-GB models into GPU/CPU memory. The current code loads models inside methods that may be called multiple times. After rearchitecting, it's easy to accidentally load models per-file instead of per-pipeline-run.

**Prevention:**
- Models should be loaded exactly once per pipeline run, managed by the pipeline, not the processor
- Use a model manager or context manager pattern: `with SuryaModels() as models:` that handles load/unload
- Never import Marker/Surya at module level -- always lazy-load behind a function boundary to keep CLI startup fast
- Add a test that mocks `create_model_dict` and asserts it's called exactly once across a multi-file run

**Phase:** Design during library API phase; implement during processor refactoring.

### Pitfall 6: CLI-to-Library Extraction Breaks Error Handling

**What goes wrong:** When extracting a library API from a CLI tool, errors that were handled by printing messages and exiting (`sys.exit(1)`, `console.print("[red]...")`) get carried into library code. Library consumers get `SystemExit` exceptions or Rich markup strings instead of proper exceptions.

**Prevention:**
- Define a clear exception hierarchy: `OCRError`, `QualityError`, `ModelLoadError`
- Library layer must never import Rich, call `console.print()`, or call `sys.exit()`
- CLI layer wraps library calls and translates exceptions to user-facing messages
- Return structured results (dataclasses/TypedDict) from library, not formatted strings
- Write tests that use the library API without any TTY -- if it raises or prints to stdout, it's a bug

**Phase:** Foundation phase -- define API boundaries before any refactoring.

### Pitfall 7: Testing OCR Pipelines Without Deterministic Fixtures

**What goes wrong:** Tests that depend on actual OCR output are flaky because: (1) Tesseract versions produce slightly different text, (2) Surya model updates change output, (3) PDF rendering varies across platforms. Teams either skip testing or write tests that break on every dependency update.

**Prevention:**
- Create small (1-3 page) synthetic test PDFs with known text (e.g., use reportlab to create PDFs with embedded text)
- Test pipeline logic separately from OCR engines: mock the OCR step, test the orchestration
- For quality analysis tests, use pre-captured OCR output strings, not live OCR
- Integration tests with real OCR should be marked `@pytest.mark.slow` and run separately
- Pin Tesseract version in CI

**Phase:** Testing infrastructure should be set up early, before refactoring begins.

### Pitfall 8: Temp File Cleanup Failures Filling Disk

**What goes wrong:** The pipeline creates work directories, batch PDFs, combined PDFs. If processing fails mid-pipeline, these aren't cleaned up. `combined_pdf.unlink(missing_ok=True)` at line 572 only runs on the happy path. Over multiple runs, the `work/` directory accumulates gigabytes of intermediate PDFs.

**Prevention:**
- Use `tempfile.TemporaryDirectory` for all intermediate files -- auto-cleanup on context exit
- Or implement explicit cleanup in a `finally` block at the pipeline level
- Add a `--clean` flag or automatic cleanup of work dirs older than N hours
- Test that temp files don't survive after both successful and failed runs

**Phase:** Address during pipeline restructure.

### Pitfall 9: Marker/Surya API Instability

**What goes wrong:** The Marker library API changes between versions. The current code imports `from marker.converters.pdf import PdfConverter` and `from marker.models import create_model_dict` -- these import paths have changed across Marker versions. A pip upgrade silently breaks the pipeline.

**Prevention:**
- Pin marker-pdf version strictly in pyproject.toml (not just `>=`)
- Wrap all Marker imports in a single adapter module with version detection
- Test imports in CI: a simple `import marker; marker.__version__` check
- Document which Marker version the code targets

**Phase:** Address during dependency management, early in the project.

## Minor Pitfalls

### Pitfall 10: ProcessPoolExecutor Serialization Constraints

**What goes wrong:** `_process_single` is a module-level function (required for pickling) that takes a tuple of `(Path, Path, dict)`. When refactoring to use classes or closures, it's easy to accidentally make this a method or lambda, which can't be pickled for multiprocessing.

**Prevention:**
- Keep process pool worker functions as module-level functions
- All arguments must be picklable -- no open file handles, no model objects, no database connections
- Test multiprocessing with `spawn` start method (default on macOS) which is stricter than `fork`

**Phase:** Keep in mind during parallel processing redesign.

### Pitfall 11: Quality Threshold as a Single Global Number

**What goes wrong:** A single `quality_threshold=0.85` treats all pages equally. Title pages, bibliography pages, and image-heavy pages naturally score low but don't need Surya. This sends many pages to Surya unnecessarily, wasting processing time.

**Prevention:**
- Consider per-page-type thresholds or minimum word count filters (pages with < 20 words are likely non-text)
- Allow threshold override per file via config
- Log which pages triggered Surya and why, so users can tune

**Phase:** Quality analysis improvements phase.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Library API design | CLI concerns leak into library (Rich, sys.exit) | Define exception hierarchy first; library must not depend on Rich |
| Pipeline restructure | Surya results still not written back | Integration test: verify output file content changes after Phase 2 |
| Pipeline restructure | Page mapping corruption | Use explicit IDs, not positional indices |
| Processor refactoring | File handle leaks | Context managers everywhere; low-ulimit stress test |
| Parallel processing | CPU/memory oversubscription | Single resource budget; configurable limits |
| ML model lifecycle | Models loaded multiple times | Model manager pattern; mock-based test for load count |
| Testing setup | Flaky OCR-dependent tests | Synthetic fixtures + mocked OCR for logic tests |
| Dependency management | Marker API breaks on upgrade | Pin version; adapter module; import tests |

## Sources

- Direct analysis of current codebase (`pipeline.py`, `processor.py`)
- PyMuPDF documentation on file handle management (HIGH confidence)
- Python multiprocessing documentation on pickling constraints (HIGH confidence)
- ocrmypdf documentation on `--jobs` flag behavior (HIGH confidence)
