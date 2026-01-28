# Codebase Structure

**Analysis Date:** 2026-01-28

## Directory Layout

```
scholardoc-ocr/
├── src/
│   └── scholardoc_ocr/
│       ├── __init__.py              # Package metadata (__version__)
│       ├── cli.py                   # CLI entry point, argument parsing
│       ├── pipeline.py              # Orchestration, Phase 1 & 2 logic
│       ├── processor.py             # PDF operations, Tesseract/Surya execution
│       └── quality.py               # Text quality analysis
├── pyproject.toml                   # Project metadata, dependencies, build config
├── README.md                        # User documentation
├── CLAUDE.md                        # Claude Code context (development instructions)
├── .gitignore                       # Git ignore rules
└── .planning/
    └── codebase/
        ├── ARCHITECTURE.md          # (This analysis)
        └── STRUCTURE.md             # (This analysis)
```

## Directory Purposes

**src/scholardoc_ocr/:**
- Purpose: Main package containing all application code
- Contains: Python modules for CLI, orchestration, processing, quality analysis
- Key files: All .py files are core to the pipeline

**.planning/codebase/:**
- Purpose: Codebase mapping documents for GSD system
- Contains: Analysis documents (ARCHITECTURE.md, STRUCTURE.md, etc.)
- Generated: Yes (by GSD mapper)
- Committed: Yes (created by development process)

## Key File Locations

**Entry Points:**
- `src/scholardoc_ocr/cli.py`: CLI entry point (main() function at lines 11-135)
  - Registered via pyproject.toml: `ocr = "scholardoc_ocr.cli:main"`
  - Builds configuration and invokes pipeline

**Configuration:**
- `pyproject.toml`: Project metadata, dependencies, entry point registration, linter config
  - Python version: >=3.11,<3.14
  - Build system: hatchling
  - Package location: src/scholardoc_ocr

**Core Logic:**
- `src/scholardoc_ocr/pipeline.py`: Orchestration (lines 293-600), worker function (lines 50-249)
  - `run_pipeline(config)`: Main orchestrator, Phase 1 parallel + Phase 2 batched Surya
  - `_process_single(args)`: Worker function, processes one PDF file

- `src/scholardoc_ocr/processor.py`: PDF manipulation (lines 41-384)
  - `PDFProcessor` class: Extract text, run Tesseract/Surya, combine/replace pages
  - Methods like `extract_text_by_page()`, `run_tesseract()`, `run_surya_batch()`

- `src/scholardoc_ocr/quality.py`: Quality analysis (lines 19-194)
  - `QualityAnalyzer` class: Regex-based text quality scoring
  - Pre-compiled patterns for garbled text detection
  - Whitelists for philosophical/academic terms

**Testing:**
- No test directory present (not yet created)
- Dev dependencies listed in pyproject.toml: pytest>=8.0.0, ruff>=0.4.0

## Naming Conventions

**Files:**
- Pattern: Lowercase with underscores (snake_case)
- Examples: `cli.py`, `pipeline.py`, `processor.py`, `quality.py`

**Directories:**
- Pattern: Lowercase with underscores
- Examples: `scholardoc_ocr` (package), `.planning` (hidden prefix for metadata)

**Classes:**
- Pattern: PascalCase
- Examples: `PDFProcessor`, `PipelineConfig`, `QualityAnalyzer`, `ProcessorConfig`

**Functions:**
- Pattern: snake_case
- Examples: `run_pipeline()`, `_process_single()`, `extract_text_by_page()`, `run_tesseract()`

**Module-level variables (module config):**
- Pattern: SCREAMING_SNAKE_CASE for constants
- Examples in quality.py: `PATTERNS`, `VALID_TERMS`, `VALID_SHORT`, `VALID_PATTERNS`

**Dataclass fields:**
- Pattern: snake_case
- Examples: `quality_threshold`, `force_tesseract`, `output_dir`, `bad_pages`

## Where to Add New Code

**New Feature (e.g., different OCR engine):**
- Primary code: `src/scholardoc_ocr/processor.py`
  - Add method to `PDFProcessor` class (e.g., `run_newengine()`)
  - Keep same signature pattern: accepts Path, outputs text/pdf, returns bool/Path
- Pipeline integration: `src/scholardoc_ocr/pipeline.py`
  - Add conditional branch in `_process_single()` or `run_pipeline()`
  - Update `ExtendedResult.method` enum values if tracking new methods

**New CLI Option:**
- Add to argument parser: `src/scholardoc_ocr/cli.py` lines 28-80
  - parser.add_argument() call, assign to PipelineConfig field
- Update `PipelineConfig`: `src/scholardoc_ocr/pipeline.py` lines 24-35
  - Add field with default value and docstring

**Quality Analysis Improvement:**
- Update regex patterns: `src/scholardoc_ocr/quality.py` lines 24-29
  - Modify `PATTERNS` list (precompiled at class load)
- Update whitelists: `src/scholardoc_ocr/quality.py` lines 33-47
  - Add terms to `VALID_TERMS` frozenset (e.g., new philosophical concepts)
  - Expand `VALID_SHORT` if needed (e.g., common abbreviations)
- Modify scoring logic: `src/scholardoc_ocr/quality.py` lines 82-165
  - `analyze()` method (single page) or `analyze_pages()` (batch)

**Tests (when created):**
- Suggested location: `tests/` at project root
  - Unit tests: `tests/test_quality.py`, `tests/test_processor.py`, etc.
  - Integration tests: `tests/test_pipeline.py`
  - Fixtures: `tests/fixtures/` for sample PDFs
- Run: `pytest` (configured in pyproject.toml)

**Utilities or Shared Helpers:**
- If general: Add to existing module (e.g., quality.py for analysis helpers)
- If OCR-specific: Add method to `PDFProcessor` class
- If pipeline-level: Add to `src/scholardoc_ocr/pipeline.py` as module-level function

## Special Directories

**.planning/codebase/:**
- Purpose: GSD (Generative System Design) codebase analysis documents
- Generated: Yes (created by /gsd:map-codebase command)
- Committed: Yes (checked in to git)
- Contents: ARCHITECTURE.md, STRUCTURE.md, STACK.md, INTEGRATIONS.md, CONVENTIONS.md, TESTING.md, CONCERNS.md (as analysis runs)

**.claude/:**
- Purpose: Claude Code context files (temporary or per-session)
- Generated: Yes
- Committed: No (.gitignore: `?? .claude/`)
- Contents: Ephemeral Claude session metadata

**src/scholardoc_ocr/ (package root):**
- Generated: No
- Committed: Yes
- __init__.py: Single line, defines `__version__` (line 3 in __init__.py)

## Module Dependencies

**Import order in codebase:**

1. CLI imports from pipeline:
   - `from .pipeline import PipelineConfig, run_pipeline`

2. Pipeline imports from processor and quality:
   - `from .processor import PDFProcessor, ProcessorConfig, ProcessingResult`
   - `from .quality import QualityAnalyzer, QualityResult`

3. Processor imports from nothing internal (only stdlib + external)
   - Uses lazy loading for fitz (PyMuPDF)

4. Quality imports from nothing internal (only stdlib)

**Dependency graph (acyclic):**
```
cli.py
  └── pipeline.py
        ├── processor.py
        │    └── (fitz, ocrmypdf, marker-pdf)
        └── quality.py
             └── (re module)
```

---

*Structure analysis: 2026-01-28*
