# Phase 1: Foundation and Data Structures - Research

**Researched:** 2026-01-28
**Domain:** Python library API design, dataclasses, typing, context managers
**Confidence:** HIGH

## Summary

This phase restructures existing code into a clean library API. The domain is standard Python (3.11+) patterns: dataclasses for result types, Protocol classes for callbacks, context managers for resource safety, and exception hierarchies. No external libraries needed beyond what exists.

The existing codebase has clear problems to fix: Rich imports at module level in pipeline.py (breaks library use), no context managers on fitz documents (resource leaks), `callable` lowercase in type hints (invalid in 3.11+), `run_surya_on_pages` is dead code (superseded by `run_surya_batch`), and `__init__.py` still says "Levinas OCR".

**Primary recommendation:** Define all new data structures and protocols in dedicated modules (`types.py`, `callbacks.py`, `exceptions.py`), refactor existing code to use context managers, and keep pipeline.py free of any Rich/UI imports.

## Standard Stack

### Core (already in project)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dataclasses | stdlib | Result types, configs | Built-in, JSON-friendly with asdict() |
| typing/Protocol | stdlib | Callback protocol | Structural subtyping, no inheritance needed |
| contextlib | stdlib | Context managers | AbstractContextManager for fitz wrappers |
| enum | stdlib | Status enums | Pipeline phases, OCR methods |
| json | stdlib | JSON serialization | For to_json() on results |
| pytest | >=8.0.0 | Testing | Already in dev deps |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| unittest.mock | stdlib | Mock fitz/ocrmypdf in tests | Unit tests for processor without real PDFs |
| time | stdlib | Timing tracking | Already used, keep for phase timings |

### No New Dependencies Needed
This phase uses only Python stdlib patterns. No new pip packages required.

## Architecture Patterns

### Recommended New Module Structure
```
src/scholardoc_ocr/
├── __init__.py          # Re-exports public API, __version__
├── types.py             # NEW: All result dataclasses, enums, configs
├── callbacks.py         # NEW: Callback protocol, LoggingCallback, event dataclasses
├── exceptions.py        # NEW: Exception hierarchy
├── pipeline.py          # MODIFIED: No Rich imports, uses callbacks
├── processor.py         # MODIFIED: Context managers on all fitz ops
├── quality.py           # UNCHANGED (phase 1 scope)
└── cli.py               # MODIFIED: Minimal - imports Rich only here
tests/
├── __init__.py
├── conftest.py          # Shared fixtures (temp dirs, mock PDFs)
├── test_types.py        # Result serialization, dataclass behavior
├── test_processor.py    # PDF operations with mocked fitz
├── test_callbacks.py    # Callback protocol compliance
└── test_exceptions.py   # Exception hierarchy
```

### Pattern 1: Dataclass Result Types with Drill-In Model
**What:** Nested dataclasses: `BatchResult` contains `FileResult` list, each contains `PageResult` list
**When to use:** All pipeline return values

```python
from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any

class OCRMethod(str, Enum):
    EXISTING = "existing"
    TESSERACT = "tesseract"
    SURYA = "surya"
    ERROR = "error"

class PipelinePhase(str, Enum):
    TESSERACT = "tesseract"
    QUALITY_ANALYSIS = "quality_analysis"
    SURYA = "surya"

@dataclass
class PageResult:
    page_number: int  # 0-indexed
    quality_score: float
    ocr_method: OCRMethod
    flagged: bool
    signal_scores: dict[str, float] = field(default_factory=dict)  # confidence, garbled_ratio, etc.
    text: str | None = None  # Optional, excluded by default

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.text is None:
            del d["text"]
        d["ocr_method"] = self.ocr_method.value
        return d

@dataclass
class FileResult:
    filename: str
    success: bool
    method: OCRMethod
    quality_score: float
    page_count: int
    pages: list[PageResult] = field(default_factory=list)
    error: str | None = None
    timings: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = {
            "filename": self.filename,
            "success": self.success,
            "method": self.method.value,
            "quality_score": self.quality_score,
            "page_count": self.page_count,
            "pages": [p.to_dict() for p in self.pages],
            "timings": self.timings,
        }
        if self.error:
            d["error"] = self.error
        return d

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

@dataclass
class BatchResult:
    files: list[FileResult] = field(default_factory=list)
    total_files: int = 0
    successful: int = 0
    failed: int = 0
    total_time: float = 0.0
    phase_timings: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": {
                "total_files": self.total_files,
                "successful": self.successful,
                "failed": self.failed,
                "total_time": self.total_time,
                "phase_timings": self.phase_timings,
            },
            "files": [f.to_dict() for f in self.files],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
```

### Pattern 2: Callback Protocol with Event Dataclasses
**What:** Protocol class defining callback interface, event dataclasses for typed events
**When to use:** Progress reporting from pipeline to any UI

```python
from typing import Protocol, runtime_checkable

@dataclass
class ProgressEvent:
    phase: PipelinePhase
    file: str | None = None
    page: int | None = None
    total_pages: int | None = None
    worker_id: int | None = None
    eta_seconds: float | None = None
    message: str = ""

@dataclass
class PhaseEvent:
    phase: PipelinePhase
    status: str  # "started", "completed"
    detail: str = ""

@dataclass
class ModelEvent:
    model_name: str
    status: str  # "loading", "loaded"

@runtime_checkable
class PipelineCallback(Protocol):
    def on_progress(self, event: ProgressEvent) -> None: ...
    def on_phase(self, event: PhaseEvent) -> None: ...
    def on_model(self, event: ModelEvent) -> None: ...

class LoggingCallback:
    """Built-in callback that logs to Python logging."""
    def __init__(self, logger_name: str = "scholardoc_ocr"):
        self._logger = logging.getLogger(logger_name)

    def on_progress(self, event: ProgressEvent) -> None:
        self._logger.info(f"[{event.phase.value}] {event.message}")

    def on_phase(self, event: PhaseEvent) -> None:
        self._logger.info(f"Phase {event.phase.value}: {event.status}")

    def on_model(self, event: ModelEvent) -> None:
        self._logger.info(f"Model {event.model_name}: {event.status}")
```

### Pattern 3: Exception Hierarchy
**What:** Base exception + specific subclasses, configurable fail-fast
```python
class ScholarDocError(Exception):
    """Base exception for all scholardoc-ocr errors."""

class OCRError(ScholarDocError):
    """OCR processing failed."""
    def __init__(self, message: str, filename: str | None = None):
        self.filename = filename
        super().__init__(message)

class PDFError(ScholarDocError):
    """PDF read/write operation failed."""

class ConfigError(ScholarDocError):
    """Invalid configuration."""

class DependencyError(ScholarDocError):
    """Required dependency not available."""
```

### Pattern 4: Context Manager for fitz Documents
**What:** Wrap all PyMuPDF document opens in context managers
```python
from contextlib import contextmanager

@contextmanager
def open_pdf(self, path: Path):
    """Context manager for PyMuPDF document."""
    doc = self.fitz.open(path)
    try:
        yield doc
    finally:
        doc.close()

# Usage in processor methods:
def extract_text_by_page(self, pdf_path: Path) -> list[str]:
    with self._open_pdf(pdf_path) as doc:
        return [page.get_text() for page in doc]
```

### Anti-Patterns to Avoid
- **Rich imports in library code:** pipeline.py currently imports Rich at module level. All Rich usage must move to cli.py or a dedicated rich_callback.py
- **sys.exit() in library code:** cli.py currently doesn't call sys.exit but pipeline.py prints errors directly to console and returns empty list. Should raise exceptions instead.
- **Bare doc.close():** Current code has doc.open/doc.close pairs without try/finally. If an exception occurs between open and close, the handle leaks.
- **lowercase `callable` in type hints:** `run_surya_batch` uses `progress_callback: callable = None` which is invalid in Python 3.11+. Must be `Callable[..., None] | None` or use Protocol.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Dataclass to dict | Custom serialization loops | `dataclasses.asdict()` + custom `to_dict()` for enum handling | asdict handles nesting automatically |
| Callback type checking | isinstance checks | `@runtime_checkable Protocol` | Structural subtyping, no forced inheritance |
| Resource cleanup | try/finally everywhere | `@contextmanager` decorator | Cleaner, composable, standard |
| Enum serialization | String constants | `str, Enum` mixin | `.value` gives string, JSON-friendly |

## Common Pitfalls

### Pitfall 1: dataclasses.asdict() Copies Everything
**What goes wrong:** `asdict()` deep-copies all fields including large text strings. For results with optional text content, this is wasteful.
**How to avoid:** Use custom `to_dict()` methods that skip None fields and handle enums explicitly. Only use `asdict()` for simple flat dataclasses.

### Pitfall 2: Protocol Runtime Checking Overhead
**What goes wrong:** Using `isinstance(cb, PipelineCallback)` in hot loops is slow with `@runtime_checkable`.
**How to avoid:** Check once at pipeline entry, not per-page. Store the validated callback reference.

### Pitfall 3: fitz Document Not Picklable
**What goes wrong:** PyMuPDF document objects can't be passed across process boundaries (ProcessPoolExecutor). Current code correctly avoids this by passing paths.
**How to avoid:** Never store fitz objects in dataclasses or results. Always pass Path objects to worker processes.

### Pitfall 4: Breaking Existing CLI
**What goes wrong:** Refactoring pipeline.py breaks cli.py imports.
**How to avoid:** Keep `PipelineConfig` and `run_pipeline` importable from pipeline.py (even if internals change). Update cli.py in same phase.

### Pitfall 5: Circular Imports
**What goes wrong:** New types.py imports from quality.py, quality.py imports from types.py.
**How to avoid:** types.py should be leaf module with zero internal imports. Other modules import from it, never the reverse.

## Code Examples

### Context Manager Refactor for processor.py
```python
# Current (resource leak risk):
doc = self.fitz.open(pdf_path)
texts = [page.get_text() for page in doc]
doc.close()  # Never reached if exception above

# Fixed:
with self._open_pdf(pdf_path) as doc:
    texts = [page.get_text() for page in doc]
```

### Removing Rich from pipeline.py
```python
# Current (top of pipeline.py):
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

# Fixed: Remove ALL Rich imports. Pipeline communicates via callback:
def run_pipeline(config: PipelineConfig, callback: PipelineCallback | None = None) -> BatchResult:
    cb = callback or LoggingCallback()
    cb.on_phase(PhaseEvent(phase=PipelinePhase.TESSERACT, status="started"))
    # ... processing ...
    cb.on_progress(ProgressEvent(
        phase=PipelinePhase.TESSERACT,
        file=path.name,
        worker_id=worker_id,
        message=f"Processing {path.name}",
    ))
```

### Dead Code to Remove
```python
# processor.py lines 335-383: run_surya_on_pages()
# Superseded by run_surya_batch() - remove entirely

# __init__.py line 1: "Levinas OCR" docstring
# Update to "scholardoc-ocr"

# pipeline.py: All console.print() calls, _print_debug_info()
# Replace with callback events
```

### Test Pattern for Processor (mocked fitz)
```python
import pytest
from unittest.mock import MagicMock, patch
from scholardoc_ocr.processor import PDFProcessor

@pytest.fixture
def mock_fitz():
    """Mock PyMuPDF for unit tests without real PDFs."""
    mock_doc = MagicMock()
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Sample academic text content."
    mock_doc.__iter__ = lambda self: iter([mock_page])
    mock_doc.__len__ = lambda self: 1
    mock_doc.__enter__ = lambda self: self
    mock_doc.__exit__ = lambda self, *args: self.close()

    mock_module = MagicMock()
    mock_module.open.return_value = mock_doc
    return mock_module

def test_extract_text_by_page(mock_fitz):
    with patch.dict("sys.modules", {"fitz": mock_fitz}):
        processor = PDFProcessor()
        processor._fitz = mock_fitz
        texts = processor.extract_text_by_page(Path("/fake/test.pdf"))
        assert len(texts) == 1
        assert "Sample" in texts[0]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `callable` lowercase type hint | `Callable` from typing or `Protocol` | Python 3.10+ | `callable` as annotation is invalid, use `Callable` or Protocol |
| `dict` return types | Dataclasses with `to_dict()`/`to_json()` | Convention | Type safety, IDE support |
| Manual resource cleanup | Context managers | Always best practice | Prevents leaks |
| `str` enums | `str, Enum` | Python 3.11 StrEnum or `(str, Enum)` | Type-safe, still JSON-friendly |

**Note on StrEnum:** Python 3.11+ has `enum.StrEnum` which is cleaner than `(str, Enum)` mixin. Use `StrEnum` since project requires Python >=3.11.

## Open Questions

1. **Cancellation mechanism for callbacks**
   - What we know: User wants cancellation support (Claude's discretion)
   - Recommendation: Add `on_progress` returning `bool` (False = cancel) or separate `CancellationToken` pattern. Simpler: callback raises `CancelledError`.

2. **Real-time quality score delivery**
   - What we know: Claude's discretion item from CONTEXT.md
   - Recommendation: Include quality scores in ProgressEvent as they're computed. No reason to defer.

3. **Public API surface in __init__.py**
   - What we know: Claude's discretion
   - Recommendation: Re-export key types: `run_pipeline`, `PipelineConfig`, `BatchResult`, `FileResult`, `PageResult`, `PipelineCallback`, `LoggingCallback`, exception classes, `__version__`. Keep processor/quality as internal.

## Sources

### Primary (HIGH confidence)
- Direct codebase analysis of all 4 modules
- Python 3.11 stdlib documentation (typing.Protocol, dataclasses, contextlib, enum.StrEnum)
- CONTEXT.md user decisions

### Notes
- All patterns recommended are stdlib Python. No external library research needed.
- Confidence is HIGH because this is standard Python API design with no ambiguous library choices.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - stdlib only, well-known patterns
- Architecture: HIGH - standard Python library design patterns
- Pitfalls: HIGH - derived from direct codebase analysis of existing bugs

**Research date:** 2026-01-28
**Valid until:** No expiry (stdlib patterns are stable)
