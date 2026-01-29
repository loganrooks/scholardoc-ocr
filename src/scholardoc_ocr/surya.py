"""Surya/Marker OCR backend with explicit model lifecycle management.

All torch and marker imports are lazy (inside function bodies only) to avoid
loading heavy ML dependencies at module import time.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from scholardoc_ocr.exceptions import SuryaError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


@dataclass
class SuryaConfig:
    """Configuration for the Surya/Marker OCR backend."""

    langs: str = "en,fr,el,la"
    force_ocr: bool = True
    batch_size: int = 50
    model_load_timeout: float = 300.0
    batch_timeout: float = 1200.0


def is_available() -> bool:
    """Check if the Marker/Surya package is installed.

    Uses importlib to avoid importing torch or any heavy dependencies.
    """
    try:
        importlib.import_module("marker")
        return True
    except ImportError:
        return False


def load_models(device: str | None = None) -> dict[str, Any]:
    """Load Surya/Marker models once for reuse across convert_pdf calls.

    Args:
        device: Optional device string (e.g. "cpu", "cuda:0"). If None,
            uses Marker's default device selection.

    Returns:
        Model dictionary suitable for passing to convert_pdf().

    Raises:
        SuryaError: If model loading fails.
    """
    try:
        from marker.models import create_model_dict  # noqa: PLC0415
    except ImportError as exc:
        raise SuryaError(
            "Marker package not installed. Install with: pip install marker-pdf",
            details={"package": "marker-pdf"},
        ) from exc

    logger.info("Loading Surya/Marker models...")
    try:
        if device is not None:
            import torch  # noqa: PLC0415

            model_dict = create_model_dict(device=torch.device(device))
        else:
            model_dict = create_model_dict()
    except Exception as exc:
        raise SuryaError(
            f"Failed to load Surya/Marker models: {exc}",
            details={"device": device},
        ) from exc

    logger.info("Surya/Marker models loaded successfully.")
    return model_dict


def convert_pdf(
    input_path: Path,
    model_dict: dict[str, Any],
    config: SuryaConfig | None = None,
    page_range: list[int] | None = None,
) -> str:
    """Convert a PDF to markdown text using Surya/Marker OCR.

    Args:
        input_path: Path to the input PDF file.
        model_dict: Pre-loaded model dictionary from load_models().
        config: Surya configuration. Uses defaults if None.
        page_range: Optional list of page indices to process.

    Returns:
        Rendered markdown text from the PDF.

    Raises:
        SuryaError: If conversion fails.
    """
    if config is None:
        config = SuryaConfig()

    try:
        from marker.converters.pdf import PdfConverter  # noqa: PLC0415
        from marker.renderers.markdown import MarkdownOutput  # noqa: PLC0415
    except ImportError as exc:
        raise SuryaError(
            "Marker package not installed. Install with: pip install marker-pdf",
            details={"package": "marker-pdf"},
        ) from exc

    converter_config = {
        "languages": config.langs.split(","),
        "force_ocr": config.force_ocr,
    }
    if page_range is not None:
        converter_config["page_range"] = page_range

    logger.debug("Converting %s with config: %s", input_path, converter_config)

    try:
        converter = PdfConverter(
            artifact_dict=model_dict,
            config=converter_config,
        )
        result: MarkdownOutput = converter(str(input_path))
        return result.markdown
    except Exception as exc:
        raise SuryaError(
            f"Surya/Marker conversion failed for {input_path}: {exc}",
            filename=str(input_path),
            details={"page_range": page_range},
        ) from exc
