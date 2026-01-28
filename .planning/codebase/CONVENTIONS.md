# Coding Conventions

**Analysis Date:** 2026-01-28

## Naming Patterns

**Files:**
- Module files: `snake_case.py` (e.g., `pipeline.py`, `quality.py`, `processor.py`)
- Package directory: `snake_case` (e.g., `scholardoc_ocr/`)

**Functions:**
- Public functions: `snake_case` (e.g., `run_pipeline()`, `extract_text()`)
- Private functions: Leading underscore + `snake_case` (e.g., `_process_single()`, `_print_debug_info()`)
- Functions should be descriptive: `extract_text_by_page()` over `extract_pages()`

**Variables:**
- Local variables: `snake_case` (e.g., `input_files`, `page_texts`, `total_pages`)
- Constants within functions: `snake_case` (no UPPER_CASE convention observed)
- Instance variables: `snake_case` with leading underscore if private (e.g., `self._fitz`)
- Dictionary keys: `snake_case` (e.g., `config_dict`, `page_results`)

**Types and Classes:**
- Classes: `PascalCase` (e.g., `PDFProcessor`, `QualityAnalyzer`, `PipelineConfig`)
- Dataclasses: `PascalCase` (e.g., `ProcessingResult`, `ProcessorConfig`, `ExtendedResult`)
- Type hints: Use modern Python 3.11+ syntax with `|` for unions (e.g., `Path | None` not `Optional[Path]`)
- Generic types: Use `list[str]` not `List[str]` (Python 3.9+ syntax)

## Code Style

**Formatting:**
- Black-compatible formatting (though not explicitly enforced with Black)
- Line length: 100 characters (configured in ruff)
- Indentation: 4 spaces (Python standard)

**Linting:**
- Tool: `ruff` (version >=0.4.0)
- Configuration location: `pyproject.toml`
- Selected rules: `E` (errors), `F` (Pyflakes), `I` (import sorting), `N` (naming), `W` (warnings)
- Example ruff invocation: `ruff check src/ && ruff format --check src/`

**Code organization:**
- Module docstring at top: `"""Module description."""`
- Imports immediately after docstring
- Classes and functions have docstrings with triple quotes
- Two blank lines between top-level definitions

## Import Organization

**Order:**
1. Standard library imports (`os`, `logging`, `pathlib`, `concurrent.futures`, `subprocess`)
2. Third-party imports (`rich`, `marker`, `pymupdf`, `ocrmypdf`)
3. Local/relative imports (`.processor`, `.quality`, `.pipeline`)
4. Conditional imports within `TYPE_CHECKING` block for forward references

**Path Aliases:**
- Relative imports used: `from .processor import PDFProcessor`
- No absolute path aliases (no `@` symbols in import statements)
- Conditional TYPE_CHECKING imports: `from typing import TYPE_CHECKING` then `if TYPE_CHECKING: import fitz`

**Example from `processor.py`:**
```python
from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import fitz
```

## Error Handling

**Patterns:**
- Broad exception catching: `except Exception as e` is common for user-facing operations
- Specific exception handling for known failures: `except subprocess.TimeoutExpired:` (processor.py:177)
- Specific exception handling for import errors: `except ImportError:` (processor.py:208-209)
- All exceptions logged: `logger.error(f"Message: {e}")` pattern used consistently
- Return `None` or `False` on error rather than raising (graceful degradation)

**Example error handling (processor.py:59-66):**
```python
def extract_text(self, pdf_path: Path) -> str:
    """Extract all text from PDF using PyMuPDF (fast, no subprocess)."""
    try:
        doc = self.fitz.open(pdf_path)
        text_parts = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(text_parts)
    except Exception as e:
        logger.warning(f"Text extraction failed for {pdf_path}: {e}")
        return ""
```

## Logging

**Framework:** Python `logging` module with `getLogger(__name__)` pattern

**Setup location:** `cli.py:85-89` - configured in `main()` function
```python
logging.basicConfig(
    level=logging.DEBUG if args.verbose else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
```

**Patterns:**
- Module-level logger: `logger = logging.getLogger(__name__)` at top of each file
- Log levels used:
  - `logger.info()` for milestone progress and major operations
  - `logger.warning()` for recoverable issues (missing files, extraction failures)
  - `logger.error()` for significant failures (OCR failed, page replacement failed)
  - `logger.debug()` rarely used; most debugging output goes through rich console
- Rich console for user-facing output: `console.print()` for progress/results, not logging

## Comments

**When to Comment:**
- Explain complex regex patterns (e.g., quality.py:24-28 PATTERNS list)
- Clarify design intent for non-obvious code (e.g., comments about jobs distribution in pipeline.py:56-59)
- Note important constraints (e.g., "0-indexed" for page numbers in processor.py docstrings)
- Avoid obvious comments: `count = len(doc)  # Get the count` is unnecessary

**Docstrings:**
- Module docstrings: One-liner at module top (e.g., `"""Main OCR pipeline with parallel processing."""`)
- Class docstrings: `"""Purpose of the class."""` format (processor.py:18-19)
- Function/method docstrings:
  - One-liner for simple functions
  - Multi-line with Args/Returns for complex functions
  - Include type information when not obvious from annotations

**Example from processor.py:97-105:**
```python
def replace_pages(self, original_path: Path, replacement_path: Path,
                  page_numbers: list[int], output_path: Path) -> bool:
    """Replace specific pages in original with pages from replacement PDF.

    Args:
        original_path: The original PDF
        replacement_path: PDF containing replacement pages (in order matching page_numbers)
        page_numbers: Which pages (0-indexed) in original to replace
        output_path: Where to save the merged result
    """
```

## Function Design

**Size:** Functions average 20-50 lines; orchestration functions (`run_pipeline()`, `_process_single()`) are longer (100-250 lines) due to multi-step workflows

**Parameters:**
- Use tuples for passing multiple values to worker functions (pipeline.py:50-52: `_process_single(args: tuple)`)
- Configuration objects preferred over many parameters (e.g., `ProcessorConfig`, `PipelineConfig`)
- Keyword arguments for optional parameters: `def run_surya_batch(..., batch_size: int = 50, progress_callback: callable = None)`

**Return Values:**
- Dataclass objects for structured results: `ExtendedResult`, `QualityResult`, `ProcessingResult`
- Tuples for multiple simple values (rare)
- `None` or boolean for optional results: `Path | None`, `bool`
- Consistent return types on all code paths

## Module Design

**Exports:**
- Classes exported: `PDFProcessor`, `ProcessorConfig`, `ProcessingResult`, `QualityAnalyzer`, `QualityResult`, `PipelineConfig`
- Functions exported: `run_pipeline()` (entry point)
- Private helpers start with underscore: `_process_single()`, `_print_debug_info()`

**Dataclass Usage (Heavily Used):**
- All configuration objects: `@dataclass` with `field()` for defaults
- All result objects: `@dataclass` for immutable result data
- Example (pipeline.py:24-35):
```python
@dataclass
class PipelineConfig:
    """Pipeline configuration."""
    input_dir: Path = field(default_factory=lambda: Path.home() / "Downloads")
    output_dir: Path = field(default_factory=lambda: Path.home() / "Downloads" / "levinas_ocr")
    quality_threshold: float = 0.85
    force_tesseract: bool = False
    debug: bool = False
    max_samples: int = 20
    max_workers: int = 4
    files: list[str] = field(default_factory=list)
```

**No barrel files:** Each module is imported explicitly by name, no `__init__.py` re-exports

## Special Patterns

**Lazy Loading (processor.py):**
- PyMuPDF (fitz) loaded on-demand via `@property`:
```python
@property
def fitz(self):
    """Lazy load PyMuPDF."""
    if self._fitz is None:
        import fitz
        self._fitz = fitz
    return self._fitz
```
- Marker/Surya imported inside methods to avoid startup cost

**Precompiled Regex (quality.py):**
- Performance-critical patterns compiled at class definition time:
```python
PATTERNS = [
    (re.compile(r"[bcdfghjklmnpqrstvwxz]{6,}", re.IGNORECASE), "consonant_cluster"),
    # ... more patterns
]
```

**Rich Console Output (pipeline.py):**
- Rich library heavily used for formatted terminal output
- Tables, panels, live progress updates: `rich.table.Table`, `rich.panel.Panel`, `rich.live.Live`
- Rich imported at module level: `from rich.console import Console`

---

*Convention analysis: 2026-01-28*
