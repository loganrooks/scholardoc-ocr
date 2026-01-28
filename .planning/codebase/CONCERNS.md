# Codebase Concerns

**Analysis Date:** 2026-01-28

## Tech Debt

**Phase 2 Surya Results Never Written Back:**
- Issue: After Surya OCR processes flagged pages in Phase 2, the mapped text results are never written to output files. `pipeline.py:564-567` checks if text files exist and logs progress, but performs no write operation.
- Files: `src/scholardoc_ocr/pipeline.py` (lines 552-567), `src/scholardoc_ocr/processor.py` (lines 309-317)
- Impact: Users receive Surya-processed page lists with improved quality scores, but output files contain unchanged Tesseract text. Phase 2 is effectively a no-op. PDF replacements never happen either.
- Fix approach: After Surya batch processing, read existing text files, replace bad pages with Surya output, and write back. Similarly, extract improved pages from Surya output and splice them into output PDFs using `replace_pages()`.

**Surya Batch Processing Discards OCR Output:**
- Issue: `processor.py:309-317` calls `converter(str(batch_pdf))` and stores result in `rendered`, but then discards it. Code re-extracts text via `extract_text_by_page(batch_pdf)`, which reads the original (pre-Surya) embedded text layer since Surya doesn't modify the PDF in-place.
- Files: `src/scholardoc_ocr/processor.py` (lines 307-324)
- Impact: Surya OCR results are completely ignored. Pages identified as needing Surya remain using their bad Tesseract text.
- Fix approach: Parse `rendered.markdown` to extract per-page text instead of re-reading the input PDF. Marker's `rendered` object contains the processed output.

**PyMuPDF Document Leaks on Exceptions:**
- Issue: Every `fitz.open()` call uses manual `.close()` without `try/finally` or context managers. If exceptions occur between open and close, file handles leak.
- Files: `src/scholardoc_ocr/processor.py` (lines 60-66, 68-77, 79-95, 97-129, 131-139, 229-243)
- Impact: Long-running operations on many files can exhaust file descriptor limits. Resource cleanup is non-deterministic.
- Fix approach: Use context managers (`with self.fitz.open(...) as doc:`) or `try/finally` blocks around all PyMuPDF operations.

**Repeated File Opens in Batch Page Combining:**
- Issue: `processor.py:232-235` opens the entire PDF for each `(pdf_path, page_num)` tuple, even if multiple tuples reference the same file. Processing 200 bad pages from 5 files opens some PDFs 40+ times.
- Files: `src/scholardoc_ocr/processor.py` (lines 215-243)
- Impact: Unnecessary I/O overhead and memory pressure. Linear scaling with bad page count instead of file count.
- Fix approach: Group page specs by file first, then open each PDF once and extract all needed pages in one pass.

**CPU Oversubscription in Parallel Processing:**
- Issue: `pipeline.py:59` divides `max_workers` by file count to set `jobs_per_file` for Tesseract, but `ProcessPoolExecutor` at line 390 also spawns `max_workers` processes. Results in `max_workers * jobs_per_file` concurrent threads, easily exceeding available CPU cores.
- Files: `src/scholardoc_ocr/pipeline.py` (lines 50-65, 390)
- Impact: Severe context switching overhead and performance degradation on machines with limited cores. Coordinating thread pool and per-process job counts is critical.
- Fix approach: Limit pool workers to number of input files or cores, then set `jobs_per_file = total_cores / pool_workers`.

## Performance Bottlenecks

**Linear Scan in Page Replacement:**
- Problem: `processor.py:114` uses `if page_num in page_numbers` where `page_numbers` is a list, causing O(n) lookup for every page iteration.
- Files: `src/scholardoc_ocr/processor.py` (lines 97-129)
- Cause: List membership testing is linear; set membership is O(1).
- Improvement path: Convert `page_numbers` to `set` at function start for O(1) lookups.

## Fragile Areas

**Dead Code Path — `run_surya_on_pages`:**
- Files: `src/scholardoc_ocr/processor.py` (lines 335-383)
- Why fragile: Method is never called from anywhere in codebase. It also loads Surya models independently instead of sharing with `run_surya_batch`, so if ever used it would cause redundant model loading.
- Safe modification: Remove entirely or mark `@deprecated` if keeping for backwards compatibility.
- Test coverage: No tests reference this method.

**Broken Recursive File Discovery:**
- Files: `src/scholardoc_ocr/cli.py` (lines 105-108)
- Why fragile: `rglob("*.pdf")` returns full paths but code extracts `.name` only, stripping directory info. If two subdirectories contain `paper.pdf`, only one gets processed. Later `config.input_dir / filename` lookup fails to find subdirectory files.
- Safe modification: Store relative paths from `input_dir` instead of just filenames, e.g., `path.relative_to(input_dir)`.
- Test coverage: No tests for recursive mode.

**Hardcoded Project References:**
- Files: `src/scholardoc_ocr/pipeline.py` (line 322: "LEVINAS OCR PIPELINE"), `src/scholardoc_ocr/pipeline.py` (line 29: default path includes "levinas_ocr")
- Why fragile: Project was renamed to `scholardoc-ocr` for general use. Leftover strings create confusion about project identity and defaults. CLI overrides the default path, but dataclass defaults are misleading.
- Safe modification: Use generic names like "SCHOLARDOC OCR PIPELINE" and "ocr_output" for defaults.
- Test coverage: UI strings are not tested.

## Type Annotation Issues

**Invalid Type Hint for Callback:**
- Issue: `processor.py:250` uses lowercase `callable` as type annotation, which is not valid for Python 3.11+. Should be `Callable` from `collections.abc` or `typing`.
- Files: `src/scholardoc_ocr/processor.py` (line 250)
- Impact: Type checkers (mypy, pyright) will error. Code runs fine at runtime but prevents proper static analysis.
- Fix approach: Add import: `from collections.abc import Callable`, change annotation to `Callable[[str, int, int], None] | None = None`.

## Code Organization

**Duplicate Imports in Function Bodies:**
- Issue: `from rich.live import Live` and `from rich.table import Table` imported inside `run_pipeline()` at lines 362-363 and 512-513, but `Table` is already imported at module level (line 15). `Live` should also be top-level.
- Files: `src/scholardoc_ocr/pipeline.py` (lines 362-363, 512-513, 15)
- Impact: Violates import conventions. Makes dependencies less clear and repeated imports add minor overhead.
- Fix approach: Move all imports to top of file.

## Exception Handling Gaps

**Broad Exception Catching Without Specificity:**
- Issue: Multiple methods catch generic `Exception` with minimal context about what failed. `pipeline.py:239-249` catches all exceptions in `_process_single` and returns error result without distinguishing between file corruption, OCR failure, or resource issues.
- Files: `src/scholardoc_ocr/pipeline.py` (239, 417), `src/scholardoc_ocr/processor.py` (64, 75, 93, 127, 138, 180, 211, 241, 331, 381)
- Impact: Difficult to debug failures. Users can't distinguish recoverable errors (disk full) from unrecoverable ones (corrupt PDF).
- Fix approach: Catch specific exceptions (`IOError`, `subprocess.TimeoutExpired`, `ImportError`, etc.) and provide actionable error messages.

## Missing Critical Features

**Quality Analysis Doesn't Account for Surya Improvements:**
- Issue: Quality scoring in `quality.py` uses regex-based garbled text detection on text layer content. Surya generates new PDFs with visual text extraction, but quality re-analysis doesn't distinguish between "bad Tesseract text" and "text Surya couldn't read visually."
- Files: `src/scholardoc_ocr/quality.py` (lines 1-194), `src/scholardoc_ocr/pipeline.py` (lines 463-579)
- Impact: After Surya processing, quality scores may still be low if the text layer wasn't improved, even if page images are correctly OCR'd by Surya. No feedback on visual OCR success.
- Priority: Medium - Phase 2 is non-functional anyway; fix this when Phase 2 is implemented.

## Test Coverage Gaps

**No Tests for Pipeline End-to-End:**
- What's not tested: Complete OCR pipeline from file input to text output. Tesseract-only path, Surya fallback path, error handling, file I/O.
- Files: No test files present in repository; no `tests/` directory.
- Risk: All critical bugs (Surya results not written, resource leaks) went undetected.
- Priority: High - All production code paths need coverage.

**No Tests for Quality Analysis:**
- What's not tested: `QualityAnalyzer` patterns on actual OCR output. Validation terms list, edge cases (empty text, single word, very long text).
- Files: No tests for `src/scholardoc_ocr/quality.py`.
- Risk: False positives/negatives in quality scoring can trigger unnecessary Surya processing or miss genuinely bad pages.
- Priority: High - Quality threshold is the core decision point.

**No Tests for PDF Manipulation:**
- What's not tested: `PDFProcessor` methods for extracting pages, combining PDFs, text extraction. Edge cases like corrupt PDFs, single-page files, very large files.
- Files: No tests for `src/scholardoc_ocr/processor.py`.
- Risk: PDF operations are fragile (file handle leaks, silent failures); without tests they regress easily.
- Priority: High - PDF operations are resource-critical.

**No Tests for CLI:**
- What's not tested: Argument parsing, file discovery (especially recursive mode), default values, error messages.
- Files: No tests for `src/scholardoc_ocr/cli.py`.
- Risk: Recursive mode is broken; no one detected it because there are no tests.
- Priority: Medium - CLI functionality must be validated.

---

*Concerns audit: 2026-01-28*
