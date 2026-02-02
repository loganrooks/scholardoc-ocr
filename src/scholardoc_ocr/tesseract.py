"""Tesseract OCR backend module wrapping ocrmypdf Python API."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TesseractConfig:
    """Configuration for Tesseract OCR processing."""

    langs: list[str] = field(default_factory=lambda: ["eng", "fra", "ell", "lat"])
    jobs: int = 4
    timeout: float = 600.0
    skip_big: int = 100


@dataclass
class TesseractResult:
    """Result of a Tesseract OCR operation."""

    success: bool
    output_path: Path | None = None
    error: str | None = None


def run_ocr(
    input_path: Path,
    output_path: Path,
    config: TesseractConfig | None = None,
) -> TesseractResult:
    """Run Tesseract OCR on a PDF file via ocrmypdf.

    Args:
        input_path: Path to input PDF.
        output_path: Path for OCR'd output PDF.
        config: Tesseract configuration. Uses defaults if None.

    Returns:
        TesseractResult indicating success or failure.
    """
    import ocrmypdf
    from ocrmypdf.exceptions import MissingDependencyError, PriorOcrFoundError

    if config is None:
        config = TesseractConfig()

    import shutil

    logger.error(
        "Worker env: PATH=%s tesseract=%s gs=%s unpaper=%s",
        os.environ.get("PATH", "UNSET"),
        shutil.which("tesseract"),
        shutil.which("gs"),
        shutil.which("unpaper"),
    )

    try:
        result = ocrmypdf.ocr(
            input_file=input_path,
            output_file=output_path,
            language=config.langs,
            redo_ocr=True,
            clean=True,
            output_type="pdfa",
            jobs=config.jobs,
            tesseract_timeout=config.timeout,
            skip_big=config.skip_big,
            progress_bar=False,
        )
        if result == ocrmypdf.ExitCode.ok:
            logger.info("Tesseract OCR completed: %s", input_path)
            return TesseractResult(success=True, output_path=output_path)
        logger.warning("Tesseract OCR returned exit code %s: %s", result, input_path)
        return TesseractResult(success=False, error=f"Exit code: {result}")
    except PriorOcrFoundError:
        logger.info("Prior OCR found, treating as success: %s", input_path)
        return TesseractResult(success=True, output_path=output_path)
    except MissingDependencyError as exc:
        logger.error("Missing dependency for Tesseract OCR: %s", exc)
        return TesseractResult(success=False, error=f"Missing dependency: {exc}")
    except Exception as exc:
        import traceback

        tb = traceback.format_exc()
        error_msg = f"{type(exc).__name__}: {exc}" if str(exc) else f"{type(exc).__name__}: {exc!r}"
        full_msg = f"{error_msg}\n{tb}"
        logger.error("Tesseract OCR failed for %s: %s", input_path, full_msg)
        return TesseractResult(success=False, error=full_msg)


def is_available() -> bool:
    """Check if ocrmypdf is available for import."""
    try:
        import ocrmypdf  # noqa: F401

        return True
    except ImportError:
        return False
