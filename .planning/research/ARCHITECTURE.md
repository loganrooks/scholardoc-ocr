# Architecture Patterns

**Domain:** Python OCR pipeline (library + CLI)
**Researched:** 2026-01-28
**Confidence:** HIGH (based on direct codebase analysis + established Python patterns)

## Current Problems

1. **`pipeline.py` conflates three concerns:** orchestration logic, worker/processing logic, and Rich UI rendering -- all in one 600-line file
2. **No library API:** `run_pipeline()` requires `PipelineConfig` with CLI-specific fields (debug, max_samples) and returns results while printing Rich output as a side effect. Impossible to use programmatically.
3. **Fragile cross-file Surya batching:** All bad pages from all files are combined into one PDF, processed, then mapped back by index. If any page fails to combine or Surya skips a page, the index mapping silently corrupts results.
4. **ProcessPoolExecutor + Surya incompatibility:** Surya/Marker loads GPU models (PyTorch). These cannot be shared across processes. Current code works only because Surya runs in the main process, but the architecture makes it unclear why.
5. **CPU oversubscription:** Each Tesseract worker gets `max_workers // num_files` jobs, but ProcessPoolExecutor already parallelizes across files. With `--workers 8` and 4 files, each ocrmypdf gets 2 threads, totaling 8 processes x 2 threads = potential 16 threads.

## Recommended Architecture

```
                        ┌─────────────┐
                        │   CLI (cli)  │  Thin: argparse -> Config -> Engine -> Renderer
                        └──────┬───────┘
                               │ calls
                        ┌──────▼───────┐
                        │   Engine     │  Library API: stateless functions, no UI
                        │  (engine.py) │  Returns typed results, raises on error
                        └──────┬───────┘
                               │ uses
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼───────┐ ┌──────▼───────┐
    │   Tesseract    │ │    Surya     │ │   Quality    │
    │  (tesseract.py)│ │  (surya.py)  │ │ (quality.py) │
    └────────────────┘ └──────────────┘ └──────────────┘
              │                │                │
    ┌─────────▼────────────────▼────────────────▼──────┐
    │                  PDF Utils (pdf.py)               │
    │  PyMuPDF wrappers: extract text, pages, combine  │
    └──────────────────────────────────────────────────┘
```

### Component Boundaries

| Component | Responsibility | Communicates With | IO |
|-----------|---------------|-------------------|----|
| **cli.py** | Argument parsing, Rich rendering, progress display | Engine only | stdin/stdout |
| **engine.py** | Orchestration: which files need what, parallel dispatch, result aggregation | Tesseract, Surya, Quality, PDF | Filesystem (reads/writes PDFs) |
| **tesseract.py** | ocrmypdf wrapper, subprocess management | PDF utils | Subprocess calls |
| **surya.py** | Marker/Surya model loading, inference, per-file batch processing | PDF utils | GPU/model loading |
| **quality.py** | Text quality scoring, page flagging | None (pure logic) | None |
| **pdf.py** | PyMuPDF operations: text extraction, page manipulation | None (PyMuPDF only) | Filesystem |

### Data Flow

```
Input PDFs
  │
  ▼
engine.process_directory(dir, config) -> list[FileResult]
  │
  ├─ Phase 1: For each file (parallel via ProcessPoolExecutor)
  │    ├─ pdf.extract_text_by_page(path) -> list[str]
  │    ├─ quality.analyze_pages(texts) -> list[QualityResult]
  │    ├─ If bad pages AND force/needed:
  │    │    tesseract.ocr_file(path) -> Path
  │    │    pdf.extract_text_by_page(ocr_path) -> list[str]
  │    │    quality.analyze_pages(texts) -> list[QualityResult]
  │    └─ Return FileResult(path, page_qualities, bad_pages, ocr_path)
  │
  ├─ Phase 2: Surya on bad pages (main process, sequential per file)
  │    ├─ surya.load_models() -> ModelDict  (once)
  │    ├─ For each file with bad pages:
  │    │    pdf.extract_pages(path, bad_pages) -> temp_pdf
  │    │    surya.ocr_pages(temp_pdf, models) -> list[str]
  │    │    Merge surya text back into file result
  │    └─ Return updated FileResults
  │
  └─ Return list[FileResult]

CLI layer:
  engine results -> Rich tables, progress bars, panels
```

**Key change: per-file Surya batching, not cross-file.** Each file's bad pages are extracted and processed independently. The model is loaded once and reused across files. This eliminates the fragile cross-file index mapping entirely.

## Patterns to Follow

### Pattern 1: Engine as Pure Library API

**What:** `engine.py` exposes functions that accept typed configs and return typed results. No printing, no Rich, no side effects beyond filesystem writes.

**Why:** Enables programmatic use (scripts, notebooks, other tools) without capturing stdout.

```python
# engine.py
@dataclass
class OCRConfig:
    quality_threshold: float = 0.85
    force_tesseract: bool = False
    max_workers: int = 4
    languages: list[str] = field(default_factory=lambda: ["eng", "fra", "ell", "lat"])

@dataclass
class PageResult:
    page_number: int       # 0-indexed
    quality_score: float
    method: str            # "existing" | "tesseract" | "surya"
    text: str

@dataclass
class FileResult:
    path: Path
    pages: list[PageResult]
    success: bool
    error: str | None = None
    time_seconds: float = 0.0

def process_file(path: Path, output_dir: Path, config: OCRConfig) -> FileResult:
    """Process a single PDF. No side effects beyond filesystem."""
    ...

def process_directory(
    input_dir: Path,
    output_dir: Path,
    config: OCRConfig,
    callback: Callable[[str, int, int], None] | None = None,
) -> list[FileResult]:
    """Process all PDFs in directory. Optional progress callback."""
    ...
```

**When:** This is the primary interface. CLI wraps it; tests call it directly.

### Pattern 2: Callback-Based Progress (Not Rich Coupling)

**What:** Engine accepts an optional `callback(event: str, current: int, total: int)` instead of importing Rich.

**Why:** CLI passes a callback that updates Rich progress bars. Tests pass None. Other consumers pass their own.

### Pattern 3: Surya Model Sharing via Main Process

**What:** Surya always runs in the main process. Tesseract runs in worker processes (it's CPU-only subprocesses anyway).

**Why:** PyTorch GPU models cannot be pickled or shared across ProcessPoolExecutor workers. Surya/Marker loads ~2GB of models. Loading per-process would be wasteful and may crash on GPU memory.

**Architecture implication:** Phase 1 (Tesseract) is embarrassingly parallel. Phase 2 (Surya) is sequential across files but uses GPU parallelism internally. This is correct and should be made explicit in the code structure.

### Pattern 4: Per-File Surya Batching

**What:** Instead of combining all bad pages from all files into one mega-PDF, process each file's bad pages independently.

```python
# In engine.py Phase 2
models = surya.load_models()  # Once
for file_result in results_needing_surya:
    bad_page_texts = surya.ocr_pages(
        file_result.path,
        file_result.bad_pages,
        models,
        work_dir,
    )
    # Merge directly -- no cross-file index mapping needed
    for page_num, text in zip(file_result.bad_pages, bad_page_texts):
        file_result.pages[page_num].text = text
        file_result.pages[page_num].method = "surya"
```

**Why:** Eliminates the fragile index mapping that breaks on partial failures. Each file is self-contained. If one file's Surya fails, others are unaffected.

## Anti-Patterns to Avoid

### Anti-Pattern 1: UI in Library Code

**What:** `run_pipeline()` currently imports Rich and renders tables/panels directly.
**Why bad:** Cannot use the pipeline from scripts, tests, or other tools without Rich output polluting stdout.
**Instead:** Engine returns data. CLI formats data. Callback for progress.

### Anti-Pattern 2: Cross-File Page Index Mapping

**What:** Current code combines pages from N files into one PDF, processes it, then maps results back by positional index.
**Why bad:** If any page fails to combine, or Surya returns fewer results than expected, all subsequent mappings are wrong. Silent data corruption.
**Instead:** Per-file Surya processing. Each file is independent.

### Anti-Pattern 3: Config Dict Serialization for Multiprocessing

**What:** Current `_process_single` takes a `tuple[Path, Path, dict]` because ProcessPoolExecutor needs picklable args, so PipelineConfig is manually converted to a dict.
**Why bad:** No type safety, easy to miss fields, duplicated field names.
**Instead:** Make config a simple frozen dataclass that's naturally picklable. Or use `ProcessorConfig` directly (it's already a dataclass).

### Anti-Pattern 4: Worker Thread Count Guessing

**What:** `jobs_per_file = max(1, max_workers // max(1, num_files))` tries to distribute CPU cores.
**Why bad:** ProcessPoolExecutor already manages parallelism. Having each ocrmypdf subprocess also use multiple threads causes oversubscription.
**Instead:** Set `jobs=1` per ocrmypdf call (one thread per subprocess). Let ProcessPoolExecutor handle the parallelism. This is simpler and avoids oversubscription. If processing fewer files than workers, increase workers to match.

## Module Structure

```
src/scholardoc_ocr/
├── __init__.py          # Public API: process_file, process_directory, OCRConfig, FileResult
├── cli.py               # argparse + Rich rendering (thin)
├── engine.py            # Orchestration: parallel Tesseract, sequential Surya, result aggregation
├── tesseract.py         # ocrmypdf subprocess wrapper
├── surya.py             # Marker/Surya model loading + inference
├── quality.py           # Text quality analysis (unchanged)
└── pdf.py               # PyMuPDF operations: text extraction, page manipulation
```

**What moves where from current code:**

| Current Location | New Location | What |
|------------------|-------------|------|
| `pipeline.py` lines 50-249 (`_process_single`) | `engine.py` | Worker function (cleaned up) |
| `pipeline.py` lines 293-600 (`run_pipeline`) | `engine.py` (logic) + `cli.py` (rendering) | Split orchestration from display |
| `pipeline.py` lines 252-291 (`_print_debug_info`) | `cli.py` | Pure display code |
| `pipeline.py` Rich imports, console, Live, Table | `cli.py` | All UI stays in CLI |
| `processor.py` `run_tesseract()` | `tesseract.py` | Tesseract-specific code |
| `processor.py` `run_surya*()` | `surya.py` | Surya-specific code |
| `processor.py` PDF methods | `pdf.py` | PyMuPDF operations |
| `processor.py` `ProcessorConfig` | Split between `engine.py` (OCRConfig) and individual modules | Config per concern |

## Build Order (Dependencies Between Components)

Build bottom-up. Each phase can be tested independently.

```
Phase 1: Foundation (no dependencies between these)
  ├── pdf.py        (extract from processor.py PDF methods)
  ├── quality.py    (already exists, minor refactor)
  └── Data types    (OCRConfig, FileResult, PageResult in engine.py or types.py)

Phase 2: OCR Backends (depend on pdf.py)
  ├── tesseract.py  (extract from processor.py, depends on pdf.py)
  └── surya.py      (extract from processor.py, depends on pdf.py)

Phase 3: Engine (depends on all above)
  └── engine.py     (orchestration, parallel dispatch, Surya model sharing)

Phase 4: CLI (depends on engine.py)
  └── cli.py        (Rich rendering wrapping engine API)

Phase 5: Public API
  └── __init__.py   (re-export engine.process_file, process_directory, configs, results)
```

**Key constraint:** Phases 1-2 can be built and tested with unit tests against real/mock PDFs. Phase 3 is integration. Phase 4 is pure presentation. Each phase produces a working, testable increment.

## Surya Model Sharing: The Core Constraint

**Why ProcessPoolExecutor cannot share GPU models:**

- PyTorch models contain CUDA tensors that are bound to a specific process's GPU context
- Python's `multiprocessing` uses `fork` or `spawn`; neither can share GPU state
- Marker's `create_model_dict()` returns non-picklable objects (model weights, CUDA handles)

**Correct approach (current code already does this, but implicitly):**

1. Phase 1 (Tesseract): ProcessPoolExecutor with N workers. Each worker spawns ocrmypdf as a subprocess. No GPU needed.
2. Phase 2 (Surya): Main process loads models once, iterates over files sequentially. Surya/PyTorch uses GPU parallelism internally (batch inference).

**Making this explicit in the architecture** prevents future developers from trying to parallelize Surya across processes (which would either crash or OOM the GPU).

## Sources

- Direct analysis of current codebase (`pipeline.py`, `processor.py`, `cli.py`, `quality.py`)
- Python `concurrent.futures` documentation (ProcessPoolExecutor pickling requirements) -- HIGH confidence
- PyTorch multiprocessing constraints (CUDA context not shareable across fork) -- HIGH confidence from established knowledge
- Python packaging best practices (src layout, `__init__.py` public API) -- HIGH confidence
