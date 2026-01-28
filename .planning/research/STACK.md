# Technology Stack

**Project:** scholardoc-ocr
**Researched:** 2026-01-28
**Note:** Context7 and WebSearch were unavailable. Versions are based on training data (cutoff ~May 2025). All version numbers are flagged for manual verification before pinning in pyproject.toml.

## Recommended Stack

### Keep: Core OCR Libraries

| Technology | Min Version | Purpose | Confidence | Why Keep |
|------------|-------------|---------|------------|----------|
| ocrmypdf | >=16.0.0 | Tesseract wrapper, PDF/A output | HIGH | Best-in-class Tesseract integration. Handles PDF text layer injection, image preprocessing (deskew, clean), and PDF/A compliance. No real alternative in Python. |
| marker-pdf | >=1.0.0 | Surya deep-learning OCR | MEDIUM | Only maintained Python package wrapping Surya models. Provides high-quality OCR for complex layouts. Version 1.x had breaking API changes from 0.x; verify current API. |
| PyMuPDF (fitz) | >=1.24.0 | PDF page manipulation, text extraction | HIGH | Fastest Python PDF library for page-level operations. extract/insert pages, read text. No serious competitor for this use case. |
| rich | >=13.0.0 | Terminal UI (progress bars, tables) | HIGH | Standard for Python CLI UIs. Keep but isolate behind an interface so library mode has no UI dependency. |

**Verdict: Keep all four.** The current stack is correct for this problem domain. There are no better alternatives worth the migration cost.

### Add: CLI Framework

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| click | >=8.1.0 | CLI argument parsing | Replace argparse. click provides better subcommand support, type validation, and --help formatting. Enables clean separation of CLI concerns from library API. Standard choice for Python CLIs distributed as packages. |

**Confidence: HIGH** -- click is the dominant Python CLI library and a clear upgrade from argparse for any non-trivial CLI.

### Add: Typing/Validation

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| pydantic | >=2.0.0 | Config validation | Replace hand-rolled dataclasses for PipelineConfig/ProcessorConfig. Provides validation, serialization, env-var loading. Useful when config crosses library/CLI boundary. |

**Confidence: MEDIUM** -- Optional. Dataclasses work fine if config stays simple. Add pydantic only if config complexity grows (e.g., YAML config files, env var overrides).

### Keep: Dev Tools

| Technology | Version | Purpose |
|------------|---------|---------|
| ruff | >=0.4.0 | Linting + formatting |
| pytest | >=8.0.0 | Testing |
| hatchling | (build) | Build backend |

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| Tesseract wrapper | ocrmypdf | pytesseract | pytesseract is lower-level, no PDF/A output, no preprocessing pipeline. ocrmypdf does everything pytesseract does plus more. |
| Deep learning OCR | marker-pdf (Surya) | EasyOCR | EasyOCR is slower, less accurate on academic text, weaker multilingual support for Latin/Greek. Surya is SOTA for this domain. |
| Deep learning OCR | marker-pdf (Surya) | PaddleOCR | Good accuracy but complex dependency chain (PaddlePaddle framework). Surya is simpler to install and better for Latin-script languages. |
| Deep learning OCR | marker-pdf (Surya) | doctr (docTR) | Decent but less mature for full-page OCR. Better for form/document field extraction than running text. |
| PDF manipulation | PyMuPDF | pypdf | pypdf is pure Python (slower), lacks PyMuPDF's rendering and fine-grained page manipulation. |
| PDF manipulation | PyMuPDF | pdfplumber | Built on pdfminer, focused on table extraction. Not suited for page-level insert/replace operations. |
| CLI framework | click | typer | Typer wraps click with type hints. Adds a dependency for marginal benefit. click is sufficient and more widely understood. |
| CLI framework | click | argparse | argparse is stdlib but verbose, poor subcommand UX, no built-in type coercion beyond basic types. |

## Library + CLI Architecture Pattern

### The Recommended Pattern

```
src/scholardoc_ocr/
    __init__.py          # Public API exports
    _pipeline.py         # Core orchestration (no UI, no CLI)
    _processor.py        # PDF processing (ocrmypdf, marker, pymupdf)
    _quality.py          # Quality analysis
    _models.py           # Shared data classes (configs, results)
    cli.py               # click CLI (thin wrapper over library API)
    py.typed             # PEP 561 marker
```

**Key principles:**

1. **Library first, CLI second.** Every feature must work via `from scholardoc_ocr import run_pipeline`. The CLI is a thin wrapper that parses args into config objects and calls the library.

2. **No UI in library code.** The pipeline should accept a callback/protocol for progress reporting, not import rich directly. The CLI provides a rich-based callback; library users provide their own or get silent operation.

3. **Underscore-prefix internal modules.** Public API is defined in `__init__.py`. Internal modules prefixed with `_` signal "don't import directly."

4. **Config objects cross the boundary.** CLI creates a `PipelineConfig`, passes it to `run_pipeline()`. This is already the pattern in the codebase -- keep it.

### Progress Reporting Pattern

```python
# In _models.py
from typing import Protocol

class ProgressCallback(Protocol):
    def on_file_start(self, path: Path, index: int, total: int) -> None: ...
    def on_file_complete(self, path: Path, result: ProcessingResult) -> None: ...
    def on_phase_change(self, phase: str) -> None: ...

# In _pipeline.py
def run_pipeline(config: PipelineConfig, progress: ProgressCallback | None = None) -> list[ProcessingResult]:
    ...

# In cli.py
class RichProgress:
    """Implements ProgressCallback using rich."""
    ...
```

**Confidence: HIGH** -- This is the standard Python library+CLI pattern (used by ruff, httpx, etc.).

### Surya Model Loading Pattern

**Problem:** Surya models are large (~1GB) and slow to load. Must load once, reuse across pages/files.

**Recommended pattern:**

```python
# In _processor.py
class SuryaProcessor:
    """Lazy-loaded Surya model manager."""

    def __init__(self):
        self._model = None

    def _ensure_loaded(self):
        if self._model is None:
            from marker.converters.pdf import PdfConverter
            self._model = PdfConverter()  # or equivalent current API

    def ocr_pages(self, pdf_path: Path, pages: list[int]) -> dict[int, str]:
        self._ensure_loaded()
        # Process all pages with the loaded model
        ...
```

**Key decisions:**
- Lazy load: Don't load Surya until a page actually fails quality threshold
- Single instance: Pipeline creates one SuryaProcessor, passes it to all workers
- Batch across files: Current design already batches flagged pages -- keep this
- Import inside method: Avoids importing torch/surya at module level (slow startup for tesseract-only runs)

**Confidence: HIGH** -- Lazy loading + single instance is the standard pattern for expensive ML models.

## Version Verification Needed

> **WARNING:** The following versions are from training data (cutoff ~May 2025). Verify before pinning.

| Package | Pinned in pyproject.toml | Verify Current |
|---------|--------------------------|----------------|
| ocrmypdf | >=16.0.0 | Check PyPI. Was at 16.x as of early 2025. |
| marker-pdf | >=1.0.0 | Check PyPI. Had major API changes between 0.x and 1.x. Verify current stable. |
| PyMuPDF | >=1.24.0 | Check PyPI. Releases frequently. Was ~1.24.x in 2025. |
| rich | >=13.0.0 | Stable. 13.x is fine. |
| click | >=8.1.0 | Stable. 8.1.x is current. |

Run `pip index versions <package>` or check PyPI to get exact latest versions.

## Installation

```bash
# Production
pip install ocrmypdf pymupdf marker-pdf rich click

# Dev
pip install ruff pytest

# Or via pyproject.toml
pip install -e ".[dev]"
```

## Sources

- Training data knowledge (May 2025 cutoff) -- LOW-MEDIUM confidence on versions
- Codebase analysis of current pyproject.toml and source code -- HIGH confidence on current usage
- General Python packaging best practices (PEP 517, src layout) -- HIGH confidence on patterns

## Summary

**Keep the current OCR stack.** ocrmypdf + marker-pdf + PyMuPDF is the right combination for this problem. There are no better alternatives worth switching to. The main improvements are architectural:

1. Add click for CLI (replace argparse)
2. Separate library API from CLI with a ProgressCallback protocol
3. Lazy-load Surya models with a single shared instance
4. Optionally add pydantic if config complexity grows
