# Architecture

**Analysis Date:** 2026-01-28

## Pattern Overview

**Overall:** Two-phase hybrid OCR pipeline with quality-gated fallback processing

**Key Characteristics:**
- Phase 1: Parallel Tesseract OCR on all files with page-level quality analysis
- Phase 2: Batched Surya OCR loaded once, applied only to pages below quality threshold
- Quality-driven routing: Pages assessed individually, only flagged pages processed by expensive model
- Multi-file batch optimization: Combines bad pages from multiple files into single Surya batch to amortize model load cost

## Layers

**CLI Layer:**
- Purpose: Argument parsing, configuration assembly, user-facing interface
- Location: `src/scholardoc_ocr/cli.py`
- Contains: Argument parser, logging setup, file discovery (recursive/specific)
- Depends on: `pipeline.PipelineConfig`, `pipeline.run_pipeline()`
- Used by: Command-line entry point (`ocr` command)

**Pipeline Orchestration Layer:**
- Purpose: Two-phase workflow coordination, result aggregation, status reporting
- Location: `src/scholardoc_ocr/pipeline.py`
- Contains: `PipelineConfig` (config dataclass), `run_pipeline()` (orchestrator), `_process_single()` (worker function), `ExtendedResult` (result dataclass)
- Depends on: `processor.PDFProcessor`, `quality.QualityAnalyzer`, `concurrent.futures.ProcessPoolExecutor`
- Used by: CLI layer; coordinates all other layers

**Processing Layer:**
- Purpose: Low-level PDF manipulation, Tesseract invocation, Surya batch processing
- Location: `src/scholardoc_ocr/processor.py`
- Contains: `PDFProcessor` class with methods for text extraction, page manipulation, OCR execution
- Depends on: PyMuPDF (fitz), ocrmypdf, marker-pdf
- Used by: Pipeline layer for actual OCR work and PDF operations

**Quality Analysis Layer:**
- Purpose: Fast text quality scoring without subprocess calls
- Location: `src/scholardoc_ocr/quality.py`
- Contains: `QualityAnalyzer` class with precompiled regex patterns, `QualityResult` dataclass
- Depends on: Python stdlib (re module)
- Used by: Pipeline layer for page-level quality assessment

## Data Flow

**Phase 1: Parallel Tesseract Processing**

1. `run_pipeline()` discovers input PDF files and creates `ProcessPoolExecutor`
2. Submits each file to `_process_single()` worker with `ProcessorConfig` dict
3. Each worker:
   - Extracts text page-by-page using `PDFProcessor.extract_text_by_page()`
   - Analyzes each page with `QualityAnalyzer.analyze_pages()`
   - If all pages pass quality threshold: copies PDF as-is, returns `ExtendedResult` with method="existing"
   - If some pages fail: runs `PDFProcessor.run_tesseract()` on entire file
   - Re-analyzes Tesseract output page-by-page
   - Returns `ExtendedResult` with bad_pages list for pages still below threshold
4. Results collected as workers complete; live progress display updates

**Phase 2: Batched Surya OCR (triggered only if Phase 1 flagged pages)**

1. Collects all bad pages from all files into tuples: `(source_pdf_path, page_number, filename)`
2. Combines all bad pages into single temporary PDF using `PDFProcessor.combine_pages_from_multiple_pdfs()`
3. Runs `PDFProcessor.run_surya_batch()` once with models loaded at start, processes in 50-page batches
4. Maps returned text back to original files by tracking (filename, page_number) relationship
5. Output text files in `output_dir/final/` remain from Phase 1, containing full Tesseract text

**State Management:**
- Configuration flows immutably through `PipelineConfig` → `ProcessorConfig` → worker functions
- Results accumulate in `ExtendedResult` list, sorted by filename before display
- Bad pages tracked as 0-indexed lists; displayed as 1-indexed to users
- Quality scores (0.0-1.0) compared against threshold to gate Surya processing

## Key Abstractions

**PipelineConfig:**
- Purpose: Centralized immutable configuration for entire pipeline
- Examples: `src/scholardoc_ocr/pipeline.py` lines 24-35
- Pattern: Dataclass with sensible defaults; passed through all layers

**ProcessorConfig:**
- Purpose: Configuration for PDF processing operations (language list, job count, threshold)
- Examples: `src/scholardoc_ocr/processor.py` lines 32-38
- Pattern: Dataclass created fresh for each worker based on PipelineConfig values

**ExtendedResult:**
- Purpose: Rich result object capturing outcome + debug metadata for single file
- Examples: `src/scholardoc_ocr/pipeline.py` lines 38-47
- Pattern: Extends `ProcessingResult` with page_qualities, bad_pages, timings for analysis

**QualityResult:**
- Purpose: Encapsulates analysis outcome for single page or document
- Examples: `src/scholardoc_ocr/quality.py` lines 8-16
- Pattern: Score (0-1), boolean flagged status, garbled count, optional sample issues/context

**PDFProcessor:**
- Purpose: Stateless utility wrapper around PyMuPDF and ocrmypdf
- Pattern: Lazy-loads fitz module; all methods accept path arguments; supports chaining operations

## Entry Points

**CLI Main:**
- Location: `src/scholardoc_ocr/cli.py` lines 11-135
- Triggers: `ocr` command (defined in pyproject.toml)
- Responsibilities: Parse args, construct PipelineConfig, call run_pipeline()

**Pipeline Run:**
- Location: `src/scholardoc_ocr/pipeline.py` lines 293-600
- Triggers: Called from cli.main()
- Responsibilities: File discovery, Phase 1 parallel execution, Phase 2 conditional Surya batching, result display

**Worker Process:**
- Location: `src/scholardoc_ocr/pipeline.py` lines 50-249
- Triggers: ProcessPoolExecutor.submit() for each file
- Responsibilities: Single-file quality assessment → Tesseract → re-assessment → page-level flagging

## Error Handling

**Strategy:** Fail-open with status reporting. Errors captured in `ExtendedResult.error` and method="error", not exceptions bubbling.

**Patterns:**
- `_process_single()` wrapped in try-except at lines 84-249, returns error result rather than raising
- `PDFProcessor` methods return boolean success or None on failure, never raise
- Logging at WARNING level for extraction failures, ERROR for OCR failures
- Worker exceptions caught in Phase 1 loop (lines 406-420); completed_count incremented even on error

## Cross-Cutting Concerns

**Logging:**
- Single logger per module via `logging.getLogger(__name__)`
- Configured via CLI with DEBUG or INFO based on --verbose flag
- Format: `%(asctime)s | %(levelname)s | %(message)s`

**Validation:**
- Quality threshold (0.0-1.0) validated implicitly; compared against scores
- PDF paths validated via existence check before processing (lines 308-313)
- Page numbers bounds-checked before extraction (e.g., processor.py line 86)

**Authentication:**
- Not applicable; no external services requiring auth in core pipeline

---

*Architecture analysis: 2026-01-28*
