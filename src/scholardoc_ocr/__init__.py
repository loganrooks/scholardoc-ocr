"""ScholarDoc OCR - Hybrid OCR pipeline for academic texts."""

__version__ = "0.1.0"

from .callbacks import LoggingCallback, NullCallback, PipelineCallback
from .exceptions import (
    ConfigError,
    DependencyError,
    OCRError,
    PDFError,
    ScholarDocError,
    SuryaError,
    TesseractError,
)
from .types import (
    BatchResult,
    FileResult,
    OCREngine,
    PageResult,
    PageStatus,
    ProcessingPhase,
)

__all__ = [
    "__version__",
    "BatchResult",
    "FileResult",
    "PageResult",
    "OCREngine",
    "ProcessingPhase",
    "PageStatus",
    "PipelineCallback",
    "LoggingCallback",
    "NullCallback",
    "ScholarDocError",
    "OCRError",
    "TesseractError",
    "SuryaError",
    "PDFError",
    "ConfigError",
    "DependencyError",
]
