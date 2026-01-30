# Phase 4: Engine Orchestration - Research

**Researched:** 2026-01-29
**Domain:** Pipeline orchestration, OCR engine coordination, parallel processing
**Confidence:** HIGH

## Summary

This phase rewrites the pipeline orchestration in `pipeline.py` to fix two bugs (Surya results never written back; Surya text extraction reads wrong source), switch from fragile cross-file page batching to per-file Surya processing with shared models, add resource-aware parallelism, and separate library orchestration from CLI presentation.

The codebase already has all the building blocks from Phases 2-3: the `surya.py` module provides `load_models()` and `convert_pdf()` with `page_range` support; `tesseract.py` provides `run_ocr()`; `types.py` has `FileResult`, `PageResult`, `BatchResult` with engine attribution and timing; `callbacks.py` has the progress protocol. The work is primarily restructuring `pipeline.py` and `cli.py`.

**Primary recommendation:** Rewrite `run_pipeline()` to process Surya per-file (not cross-file), use the Phase 3 backend modules directly, and return `BatchResult` with full page-level detail.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `concurrent.futures` | stdlib | ProcessPoolExecutor for Phase 1 parallelism | Already used, proven |
| `scholardoc_ocr.surya` | local | `load_models()` + `convert_pdf(page_range=...)` | Phase 3 module, supports per-file page ranges |
| `scholardoc_ocr.tesseract` | local | `run_ocr()` | Phase 3 module |
| `scholardoc_ocr.types` | local | `FileResult`, `PageResult`, `BatchResult`, `OCREngine` | Phase 2 types |
| `multiprocessing` | stdlib | `cpu_count()` for auto-detection | Already used in cli.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `os` | stdlib | `os.cpu_count()` for worker calculation | Resource-aware parallelism |
| `dataclasses` | stdlib | Config and result types | Already used throughout |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ProcessPoolExecutor | asyncio | Tesseract is CPU-bound subprocess; ProcessPool is correct |
| Sequential Surya | Parallel Surya | Surya uses GPU/full CPU; parallel would OOM. Sequential per-file is correct |

## Architecture Patterns

### Recommended Module Structure
```
src/scholardoc_ocr/
├── pipeline.py          # Library API: run_pipeline() returns BatchResult
├── cli.py               # CLI presentation: argparse, print summary, exit codes
├── tesseract.py         # Backend: run_ocr()
├── surya.py             # Backend: load_models(), convert_pdf()
├── processor.py         # PDF manipulation: extract_text_by_page, get_page_count
├── quality.py           # Quality analysis
├── types.py             # FileResult, PageResult, BatchResult
├── callbacks.py         # PipelineCallback protocol
└── exceptions.py        # Error hierarchy
```

### Pattern 1: Per-File Surya Processing (eliminates cross-file mapping)
**What:** Instead of combining bad pages from all files into one PDF, process each file individually with `convert_pdf(input_path, models, page_range=bad_pages)`.
**When to use:** Always -- this is the core architecture change.
**Example:**
```python
# Current (broken): combine all bad pages across files into one PDF
combined_pdf = combine_pages_from_multiple_pdfs(page_specs, combined_pdf)
surya_texts = run_surya_batch(combined_pdf, ...)  # returns list of texts
# Then fragile index mapping back to original files

# New: per-file processing with shared models
models = surya.load_models()
for file_result in needs_surya:
    markdown = surya.convert_pdf(
        file_result.input_path,
        models,
        page_range=file_result.bad_pages,
    )
    # markdown is for THIS file's bad pages only -- no cross-file mapping needed
```

### Pattern 2: Two-Phase Pipeline with Shared Model Lifecycle
**What:** Phase 1 runs Tesseract in parallel (ProcessPoolExecutor). Phase 2 loads Surya models once, then processes flagged files sequentially.
**When to use:** This is the existing pattern, kept but fixed.
**Example:**
```python
def run_pipeline(config, callback=None) -> BatchResult:
    # Phase 1: Parallel Tesseract
    with ProcessPoolExecutor(max_workers=effective_workers) as pool:
        phase1_results = [pool.submit(_tesseract_worker, ...) for f in files]

    # Phase 2: Sequential Surya (models loaded once)
    flagged = [r for r in phase1_results if r.bad_pages]
    if flagged:
        models = surya.load_models()
        for file_result in flagged:
            _surya_enhance(file_result, models, ...)

    return BatchResult(files=all_results, ...)
```

### Pattern 3: Resource-Aware Worker Calculation
**What:** `effective_workers = total_cores // jobs_per_file` to avoid oversubscription when ocrmypdf uses multiple threads internally.
**When to use:** When configuring the ProcessPoolExecutor.
**Example:**
```python
total_cores = os.cpu_count() or 4
jobs_per_file = max(1, total_cores // max(1, len(files)))
pool_workers = max(1, total_cores // jobs_per_file)
# Ensures: pool_workers * jobs_per_file <= total_cores
```

### Pattern 4: Library vs CLI Separation
**What:** `run_pipeline()` returns `BatchResult` (data only). CLI formats and prints.
**When to use:** Always -- enables testing and programmatic use.
**Example:**
```python
# pipeline.py (library)
def run_pipeline(config: PipelineConfig, callback=None) -> BatchResult:
    ...
    return BatchResult(files=results, total_time_seconds=elapsed)

# cli.py (presentation)
def main():
    ...
    batch = run_pipeline(config, callback=RichCallback())
    _print_summary(batch)
    sys.exit(0 if batch.error_count == 0 else 1)
```

### Anti-Patterns to Avoid
- **Cross-file page index mapping:** The current approach combines pages from multiple files into one PDF, then maps Surya output back by index. This is fragile and the source of BUG-02. Use per-file processing instead.
- **Discarding Surya results:** The current code (pipeline.py:437-446) finds the text file but never writes Surya text into it. Must actually write results.
- **print() in library code:** Pipeline should use callbacks/logging only. All `print()` stays in cli.py.
- **Returning ExtendedResult:** Phase 2 types (`FileResult`, `PageResult`) already exist with engine attribution and timing. Don't keep the old `ExtendedResult`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Per-page Surya text | Split combined PDF markdown by page breaks | `convert_pdf(page_range=[...])` per file | Marker's `page_range` param handles this natively |
| Result types | New dataclasses | `FileResult`, `PageResult`, `BatchResult` from types.py | Already designed with engine attribution, timing, JSON serialization |
| Progress reporting | print/logging inline | `PipelineCallback` protocol from callbacks.py | Already has `on_progress`, `on_phase`, `on_model` |
| Model lifecycle events | Ad-hoc logging | `ModelEvent` from callbacks.py | Already exists |
| Error handling | Generic Exception | `SuryaError`, `TesseractError` from exceptions.py | Phase 2 hierarchy already built |

**Key insight:** Phases 2-3 built all the infrastructure. This phase assembles it. Resist creating new types or abstractions.

## Common Pitfalls

### Pitfall 1: Surya Markdown Contains All Pages as One Blob
**What goes wrong:** `convert_pdf()` returns a single markdown string. If processing multiple pages with `page_range`, you get one string, not one per page.
**Why it happens:** Marker renders the entire document as continuous markdown.
**How to avoid:** For per-page text replacement in the output .txt file, split the markdown by page separators (e.g., `\n---\n` or similar markers) or accept that Surya replaces a contiguous range of page text. Alternatively, call `convert_pdf()` once per bad page (slower but gives exact per-page text). Best approach: call once per file with all bad pages, then replace the concatenated bad-page section in the output text.
**Warning signs:** All bad pages get identical text; text doesn't match expected page.

### Pitfall 2: ProcessPoolExecutor + Surya Model Sharing
**What goes wrong:** Trying to pass Surya models to worker processes fails (models contain CUDA tensors, not picklable).
**Why it happens:** ProcessPoolExecutor serializes arguments with pickle.
**How to avoid:** Surya must run in the main process (or a single dedicated process). Phase 1 (Tesseract) uses the pool; Phase 2 (Surya) runs sequentially in main process.
**Warning signs:** PicklingError on model dict.

### Pitfall 3: Forgetting to Write Back Surya Results (BUG-01)
**What goes wrong:** Surya processes pages successfully but output files still contain only Tesseract text.
**Why it happens:** Current code at pipeline.py:437-446 checks `if text_path.exists()` but never writes the new text.
**How to avoid:** After `convert_pdf()`, explicitly read existing .txt, replace bad-page text sections, write back. Also update the output PDF if needed.
**Warning signs:** Output files unchanged after Surya phase.

### Pitfall 4: Page Number Off-By-One
**What goes wrong:** Surya processes wrong pages or text gets written to wrong position.
**Why it happens:** PyMuPDF uses 0-indexed pages; Marker's `page_range` also uses 0-indexed. But display/logging uses 1-indexed.
**How to avoid:** Internally always 0-indexed. Only convert to 1-indexed for display/logging.
**Warning signs:** First or last page text is wrong; logs show page N but content is from page N-1.

### Pitfall 5: Partial Failure Handling
**What goes wrong:** If Surya fails on one file, all Surya results are lost.
**Why it happens:** Processing all files in one try/except block.
**How to avoid:** Per-file try/except in the Surya loop. On failure, keep Tesseract output for that file, log error, continue to next file.
**Warning signs:** One bad file causes all Surya-flagged files to keep Tesseract output.

## Code Examples

### Core Pipeline Rewrite Pattern
```python
def run_pipeline(config: PipelineConfig, callback: PipelineCallback | None = None) -> BatchResult:
    cb = callback or NullCallback()
    start = time.time()

    # Phase 1: Parallel Tesseract
    total_cores = os.cpu_count() or 4
    jobs_per_file = max(1, total_cores // max(1, len(files)))
    pool_workers = max(1, total_cores // jobs_per_file)

    cb.on_phase(PhaseEvent(phase="tesseract", status="started", ...))
    file_results: list[FileResult] = []
    with ProcessPoolExecutor(max_workers=pool_workers) as pool:
        futures = {pool.submit(_tesseract_worker, f, config, jobs_per_file): f for f in files}
        for future in as_completed(futures):
            result = future.result()
            file_results.append(result)
            cb.on_progress(ProgressEvent(phase="tesseract", ...))
    cb.on_phase(PhaseEvent(phase="tesseract", status="completed", ...))

    # Phase 2: Sequential Surya for flagged files
    flagged = [r for r in file_results if r.flagged_pages]
    if flagged:
        cb.on_phase(PhaseEvent(phase="surya", status="started", ...))
        cb.on_model(ModelEvent(model_name="surya", status="loading"))
        models = surya.load_models()
        cb.on_model(ModelEvent(model_name="surya", status="loaded"))

        for fr in flagged:
            try:
                bad_indices = [p.page_number for p in fr.flagged_pages]
                markdown = surya.convert_pdf(input_path, models, page_range=bad_indices)
                _writeback_surya_results(fr, markdown, bad_indices, output_dir)
                cb.on_progress(ProgressEvent(phase="surya", ...))
            except SuryaError as e:
                logger.warning("Surya failed for %s: %s", fr.filename, e)
                # Keep Tesseract output (partial success)

        cb.on_phase(PhaseEvent(phase="surya", status="completed", ...))

    return BatchResult(files=file_results, total_time_seconds=time.time() - start)
```

### Writeback Pattern
```python
def _writeback_surya_results(
    file_result: FileResult,
    surya_markdown: str,
    bad_page_indices: list[int],
    output_dir: Path,
) -> None:
    """Write Surya-enhanced text back to output files."""
    text_path = output_dir / "final" / f"{Path(file_result.filename).stem}.txt"

    # Read existing page texts
    page_texts = list(existing_page_texts)  # from Tesseract output

    # Replace bad pages with Surya text
    # Note: surya_markdown is one blob for all bad pages
    # Split strategy depends on whether we can identify page breaks
    for i, page_idx in enumerate(bad_page_indices):
        page_texts[page_idx] = surya_markdown  # simplified; see pitfall 1

    # Write back
    text_path.write_text("\n\n".join(page_texts), encoding="utf-8")

    # Update FileResult page entries
    for page_idx in bad_page_indices:
        file_result.pages[page_idx].engine = OCREngine.SURYA
```

### Tesseract Worker Pattern
```python
def _tesseract_worker(input_path: Path, config: dict, jobs: int) -> FileResult:
    """Worker function for ProcessPoolExecutor (must be picklable)."""
    # ... run tesseract, analyze quality, build FileResult with PageResults
    # Returns FileResult with bad pages flagged
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Cross-file combined PDF for Surya | Per-file `convert_pdf(page_range=...)` | Phase 3 (surya.py) | Eliminates index mapping bug |
| `PDFProcessor.run_surya_batch()` | `surya.convert_pdf()` | Phase 3 refactor | Clean module boundary |
| `ExtendedResult` + `ProcessingResult` | `FileResult` + `PageResult` + `BatchResult` | Phase 2 (types.py) | Engine attribution, timing, JSON serialization |
| Inline print/logging | `PipelineCallback` protocol | Phase 2 (callbacks.py) | Library/CLI separation |

## Open Questions

1. **Surya markdown page splitting**
   - What we know: `convert_pdf()` returns one markdown string for all requested pages. Marker does not insert explicit page break markers.
   - What's unclear: Whether calling `convert_pdf()` per-page (instead of per-file with page_range) produces better results or is too slow.
   - Recommendation: Start with one `convert_pdf()` call per file with all bad pages. If page-level granularity is needed for the before/after quality comparison, call per-page. Profile to decide.

2. **--force-surya implementation scope**
   - What we know: User wants a separate flag that runs Surya regardless of quality.
   - What's unclear: Whether it should skip Tesseract entirely or still run Tesseract first then force Surya on all pages.
   - Recommendation: Run Tesseract first (for baseline), then force Surya on all pages. This gives before/after quality comparison data.

3. **Output PDF update**
   - What we know: Current code copies Tesseract PDF to final/. Surya produces markdown, not PDF.
   - What's unclear: Whether the output PDF should be updated with Surya-processed pages.
   - Recommendation: Phase 4 focuses on .txt output. PDF enhancement can be deferred unless user specifically requested it.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis: `pipeline.py`, `surya.py`, `tesseract.py`, `processor.py`, `types.py`, `callbacks.py`, `exceptions.py`, `cli.py`
- Bug identification from code: BUG-01 at pipeline.py:437-446, BUG-02 eliminated by per-file approach

### Secondary (MEDIUM confidence)
- Marker `PdfConverter` API: `config["page_range"]` parameter observed in `surya.py:121` and tested in `test_surya.py:157-189`

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in codebase, no new dependencies
- Architecture: HIGH - patterns derived directly from existing code and Phase 2-3 infrastructure
- Pitfalls: HIGH - bugs identified from code analysis, parallelism constraints from Python stdlib behavior

**Research date:** 2026-01-29
**Valid until:** 2026-03-01 (stable domain, no external dependency changes expected)
