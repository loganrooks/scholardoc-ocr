# Phase 3: OCR Backend Modules - Research

**Researched:** 2026-01-29
**Domain:** OCR backend extraction / module decomposition
**Confidence:** HIGH

## Summary

This phase extracts Tesseract and Surya OCR operations from the monolithic `PDFProcessor` class (processor.py) into two focused backend modules: `tesseract.py` and `surya.py`. The current codebase has both OCR engines embedded as methods on `PDFProcessor` alongside PDF manipulation utilities. The extraction is straightforward because the OCR methods have clear boundaries and minimal coupling to the PDF manipulation code.

Key findings: (1) ocrmypdf has a proper Python API (`ocrmypdf.ocr()`) that should replace the current subprocess call, giving better error handling and timeout control via `tesseract_timeout` parameter; (2) Marker's `create_model_dict()` supports explicit device/dtype configuration, enabling proper lifecycle management; (3) the `PdfConverter` accepts `page_range` config for selective page processing, which could simplify batch processing.

**Primary recommendation:** Create `tesseract.py` and `surya.py` as function-based modules (not classes), keep `PDFProcessor` as a thin facade for PDF manipulation only, and use ocrmypdf's Python API instead of subprocess.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| ocrmypdf | >=16.0.0 | Tesseract OCR wrapper | Already a dependency; has Python API `ocrmypdf.ocr()` |
| marker-pdf | >=1.0.0 | Surya/Marker OCR | Already a dependency; `PdfConverter` + `create_model_dict()` |
| pymupdf | >=1.24.0 | PDF manipulation | Already a dependency; stays in processor.py |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=8.0.0 | Testing | Unit + integration tests with marks |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| ocrmypdf Python API | subprocess (current) | Subprocess gives isolation but loses structured errors; Python API is cleaner |
| Function modules | Class-based backends | Classes add unnecessary state; functions are simpler for stateless Tesseract and can still manage Surya models via closure or passed-in dict |

## Architecture Patterns

### Recommended Module Structure
```
src/scholardoc_ocr/
├── processor.py      # PDF manipulation only (extract/replace/combine pages, text extraction)
├── tesseract.py      # Tesseract OCR via ocrmypdf Python API
├── surya.py          # Surya/Marker OCR with model lifecycle
├── quality.py        # (existing)
├── pipeline.py       # Orchestrator imports from tesseract/surya directly
├── callbacks.py      # (existing)
└── cli.py            # (existing)
```

### Pattern 1: Stateless Function Module (tesseract.py)
**What:** Module-level functions wrapping ocrmypdf, no class needed since Tesseract is stateless (subprocess-based).
**When to use:** For operations with no persistent state.
**Example:**
```python
# tesseract.py
from __future__ import annotations
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class TesseractConfig:
    langs: list[str]  # e.g. ["eng", "fra", "ell", "lat"]
    jobs: int = 4
    timeout: float = 600.0  # seconds per file
    skip_big: int = 100  # megapixels

@dataclass
class TesseractResult:
    success: bool
    output_path: Path | None = None
    error: str | None = None

def run_ocr(input_path: Path, output_path: Path, config: TesseractConfig) -> TesseractResult:
    """Run Tesseract OCR via ocrmypdf Python API."""
    try:
        import ocrmypdf
        result = ocrmypdf.ocr(
            str(input_path),
            str(output_path),
            language=config.langs,
            redo_ocr=True,
            clean=True,
            output_type="pdfa",
            jobs=config.jobs,
            tesseract_timeout=config.timeout,
            skip_big=config.skip_big,
            progress_bar=False,
        )
        return TesseractResult(success=(result == 0), output_path=output_path)
    except ocrmypdf.exceptions.PriorOcrFoundError:
        return TesseractResult(success=True, output_path=output_path)
    except Exception as e:
        return TesseractResult(success=False, error=str(e))

def is_available() -> bool:
    """Check if Tesseract/ocrmypdf is available."""
    try:
        import ocrmypdf  # noqa: F401
        return True
    except ImportError:
        return False
```
Source: Context7 /ocrmypdf/ocrmypdf - Python API docs

### Pattern 2: Model-Lifecycle Module (surya.py)
**What:** Module with lazy model loading, explicit model dict management, and batch conversion.
**When to use:** For ML-backed operations where model loading is expensive and must happen once.
**Example:**
```python
# surya.py
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

@dataclass
class SuryaConfig:
    langs: str = "en,fr,el,la"
    force_ocr: bool = True
    batch_size: int = 50
    model_load_timeout: float = 300.0  # seconds
    batch_timeout: float = 1200.0  # seconds

def load_models(device: str | None = None) -> dict[str, Any]:
    """Load Surya/Marker models. Call once per pipeline run."""
    from marker.models import create_model_dict
    if device:
        import torch
        return create_model_dict(device=torch.device(device))
    return create_model_dict()

def convert_pdf(
    input_path: Path,
    model_dict: dict[str, Any],
    config: SuryaConfig,
    page_range: list[int] | None = None,
) -> str | None:
    """Convert PDF to text using pre-loaded models."""
    from marker.converters.pdf import PdfConverter
    from marker.output import text_from_rendered

    converter_config = {
        "langs": config.langs,
        "force_ocr": config.force_ocr,
    }
    if page_range is not None:
        converter_config["page_range"] = page_range

    converter = PdfConverter(artifact_dict=model_dict, config=converter_config)
    rendered = converter(str(input_path))
    text, _, _ = text_from_rendered(rendered)
    return text

def is_available() -> bool:
    """Check if Marker/Surya is available without importing torch."""
    try:
        import importlib
        importlib.import_module("marker")
        return True
    except ImportError:
        return False
```
Source: Context7 /datalab-to/marker - PdfConverter API, create_model_dict

### Pattern 3: Configurable Timeouts
**What:** Different default timeouts per operation type, all overridable.
**Example:**
```python
# Default timeouts (seconds)
TESSERACT_FILE_TIMEOUT = 600.0    # 10 min per file
SURYA_MODEL_LOAD_TIMEOUT = 300.0  # 5 min for model loading
SURYA_BATCH_TIMEOUT = 1200.0      # 20 min per batch of 50 pages
```

### Anti-Patterns to Avoid
- **Importing torch/marker at module level:** This triggers GPU initialization and multi-GB model downloads. All ML imports must be inside functions.
- **Creating PdfConverter per page:** The converter setup is expensive. Create once with model_dict and reuse.
- **Catching broad Exception for ocrmypdf:** Use specific `ocrmypdf.exceptions.*` for actionable error handling.
- **Loading models in subprocess workers:** Surya models must load in the main process and be shared. Loading per-worker wastes GPU memory.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tesseract subprocess management | Shell command builder | `ocrmypdf.ocr()` Python API | Handles process lifecycle, timeouts, error codes properly |
| Surya model loading | Custom model caching | `create_model_dict()` | Handles device detection, dtype selection, model registry |
| PDF page selection for Surya | Extract pages to temp PDF | `page_range` config in PdfConverter | Built-in page selection avoids temp file overhead |
| Dependency checking | Try/except ImportError everywhere | Centralized `is_available()` per module | Single place to check, clean error messages |

**Key insight:** Both ocrmypdf and Marker have well-designed Python APIs that handle the hard parts (process management, model loading, device selection). The backends should be thin wrappers around these APIs, not reimplementations.

## Common Pitfalls

### Pitfall 1: Importing torch at module level
**What goes wrong:** `import torch` at top of surya.py triggers CUDA initialization, taking seconds even when Surya isn't needed.
**Why it happens:** Standard Python import conventions.
**How to avoid:** All torch/marker imports inside function bodies. Use `TYPE_CHECKING` for type hints only.
**Warning signs:** Slow CLI startup even for `--help`.

### Pitfall 2: Model dict not shared across converter instances
**What goes wrong:** Each `PdfConverter()` call loads fresh models if artifact_dict isn't passed.
**Why it happens:** Marker's default behavior is to create models if not provided.
**How to avoid:** Always pass `artifact_dict=model_dict` to PdfConverter. Load models once via `load_models()`, pass the dict into every `convert_pdf()` call.
**Warning signs:** GPU OOM errors, 30+ second delays between files.

### Pitfall 3: ocrmypdf.ocr() requires main-guard on macOS
**What goes wrong:** Multiprocessing crash on macOS without `if __name__ == '__main__'` guard.
**Why it happens:** macOS uses spawn (not fork) for multiprocessing.
**How to avoid:** The Tesseract backend runs within ProcessPoolExecutor workers, which already handle this. But if testing directly, use the main guard.
**Warning signs:** `RuntimeError: An attempt has been made to start a new process...`

### Pitfall 4: PdfConverter config dict vs ConfigParser
**What goes wrong:** Using wrong config format, missing settings.
**Why it happens:** Marker has two config paths: raw dict or ConfigParser. The simple dict approach works for basic usage.
**How to avoid:** Use the simple dict config `{"langs": ..., "force_ocr": True}` for our use case. Only use ConfigParser if needing advanced features (JSON output, custom processors).
**Warning signs:** TypeError or ignored settings.

### Pitfall 5: Subprocess timeout vs ocrmypdf timeout
**What goes wrong:** Current code uses `subprocess.run(timeout=600)` which kills the entire process. ocrmypdf's `tesseract_timeout` is per-page, more granular.
**Why it happens:** Subprocess timeout is a blunt instrument.
**How to avoid:** Use `ocrmypdf.ocr(tesseract_timeout=...)` for per-page timeout, plus an outer timeout for the entire call if needed.
**Warning signs:** Entire file processing killed when only one page is slow.

## Code Examples

### Using ocrmypdf Python API (replacing subprocess)
```python
# Source: Context7 /ocrmypdf/ocrmypdf
import ocrmypdf

try:
    result = ocrmypdf.ocr(
        'input.pdf', 'output.pdf',
        language=['eng', 'fra', 'ell', 'lat'],
        redo_ocr=True,
        clean=True,
        output_type='pdfa',
        jobs=4,
        tesseract_timeout=300,  # per-page timeout
        skip_big=100,
        progress_bar=False,
    )
    success = (result == 0)
except ocrmypdf.exceptions.MissingDependencyError as e:
    # Tesseract not installed
    ...
except ocrmypdf.exceptions.PriorOcrFoundError:
    # Already has OCR - not an error for us
    ...
```

### Marker model loading and conversion
```python
# Source: Context7 /datalab-to/marker
from marker.models import create_model_dict
from marker.converters.pdf import PdfConverter
from marker.output import text_from_rendered

# Load once
model_dict = create_model_dict()

# Convert multiple files with same models
for pdf_path in pdf_files:
    converter = PdfConverter(
        artifact_dict=model_dict,
        config={"langs": "en,fr,el,la", "force_ocr": True},
    )
    rendered = converter(str(pdf_path))
    text, _, _ = text_from_rendered(rendered)
```

### Marker with page_range for selective OCR
```python
# Source: Context7 /datalab-to/marker - Advanced config
from marker.converters.pdf import PdfConverter
from marker.config.parser import ConfigParser

config = {
    "force_ocr": True,
    "page_range": [0, 5, 6, 7],  # Only process these pages
}
config_parser = ConfigParser(config)

converter = PdfConverter(
    config=config_parser.generate_config_dict(),
    artifact_dict=model_dict,
    processor_list=config_parser.get_processors(),
    renderer=config_parser.get_renderer(),
)
rendered = converter("/path/to/file.pdf")
```

### Test pattern for mocked backend
```python
# Unit test - mock the underlying library
from unittest.mock import patch, MagicMock
from scholardoc_ocr.tesseract import run_ocr, TesseractConfig

def test_tesseract_success(tmp_path):
    config = TesseractConfig(langs=["eng"])
    input_pdf = tmp_path / "input.pdf"
    output_pdf = tmp_path / "output.pdf"
    # Create minimal PDF fixture...

    with patch("scholardoc_ocr.tesseract.ocrmypdf") as mock_ocr:
        mock_ocr.ocr.return_value = 0
        result = run_ocr(input_pdf, output_pdf, config)
        assert result.success
        mock_ocr.ocr.assert_called_once()
```

### Integration test with pytest marks
```python
import pytest

@pytest.mark.integration
@pytest.mark.skipif(not is_tesseract_available(), reason="Tesseract not installed")
def test_tesseract_real_pdf(real_scanned_pdf, tmp_path):
    config = TesseractConfig(langs=["eng"])
    result = run_ocr(real_scanned_pdf, tmp_path / "out.pdf", config)
    assert result.success
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `subprocess.run(["ocrmypdf", ...])` | `ocrmypdf.ocr()` Python API | ocrmypdf 14+ | Structured errors, per-page timeout, no shell dependency |
| `marker.convert_single_pdf()` | `PdfConverter(artifact_dict=...)` | marker-pdf 1.0 | Explicit model lifecycle, page_range support |
| Monolithic model loading | `create_model_dict(device=..., dtype=...)` | marker-pdf 1.0 | GPU/CPU/dtype control, separates loading from conversion |

**Deprecated/outdated:**
- `marker.convert_single_pdf()`: Old API, replaced by `PdfConverter` class in marker-pdf 1.0+
- `subprocess.run` for ocrmypdf: Works but loses structured error handling and per-page timeout

## Open Questions

1. **PdfConverter page_range vs extract-pages-to-temp-PDF**
   - What we know: Marker's `page_range` config can select pages. Current code extracts pages to temp PDF.
   - What's unclear: Whether `page_range` works reliably with `force_ocr=True` and returns per-page text
   - Recommendation: Try `page_range` first; fall back to extract-pages if it doesn't give per-page granularity

2. **ocrmypdf.ocr() in ProcessPoolExecutor workers**
   - What we know: ocrmypdf docs say use `if __name__ == '__main__'` guard on macOS
   - What's unclear: Whether calling `ocrmypdf.ocr()` (which itself spawns subprocesses) inside a `ProcessPoolExecutor` worker is safe
   - Recommendation: Test this in integration tests. If problematic, keep subprocess approach as fallback

3. **Marker ConfigParser vs raw dict**
   - What we know: Simple dict config works for basic usage. ConfigParser needed for `page_range`
   - What's unclear: Exact boundary of what simple dict supports in marker-pdf >=1.0
   - Recommendation: Start with simple dict, use ConfigParser only if page_range requires it

## Sources

### Primary (HIGH confidence)
- Context7 /ocrmypdf/ocrmypdf - Python API (`ocrmypdf.ocr()`), exceptions, timeout configuration
- Context7 /datalab-to/marker - `PdfConverter`, `create_model_dict()`, `text_from_rendered()`, config options, page_range

### Secondary (MEDIUM confidence)
- Existing codebase: processor.py, pipeline.py, callbacks.py, tests/ (direct code analysis)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - using existing project dependencies, verified APIs via Context7
- Architecture: HIGH - straightforward extraction with clear boundaries visible in current code
- Pitfalls: HIGH - verified against actual API docs (ocrmypdf exceptions, marker model lifecycle)

**Research date:** 2026-01-29
**Valid until:** 2026-02-28 (stable libraries, no fast-moving changes expected)
