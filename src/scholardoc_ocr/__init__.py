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
from .pipeline import PipelineConfig, run_pipeline
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
    # Types
    "BatchResult",
    "FileResult",
    "PageResult",
    "OCREngine",
    "ProcessingPhase",
    "PageStatus",
    # Callbacks
    "PipelineCallback",
    "LoggingCallback",
    "NullCallback",
    # Exceptions
    "ScholarDocError",
    "OCRError",
    "TesseractError",
    "SuryaError",
    "PDFError",
    "ConfigError",
    "DependencyError",
    # Pipeline API
    "PipelineConfig",
    "run_pipeline",
    # OCR backend submodules (access via scholardoc_ocr.tesseract / scholardoc_ocr.surya)
    "tesseract",
    "surya",
]
