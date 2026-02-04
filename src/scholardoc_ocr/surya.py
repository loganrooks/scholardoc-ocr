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


def load_models(device: str | None = None) -> tuple[dict[str, Any], str]:
    """Load Surya/Marker models once for reuse across convert_pdf calls.

    Args:
        device: Optional device string (e.g. "cpu", "cuda:0"). If None,
            auto-detects the best available device using detect_device().

    Returns:
        Tuple of (model_dict, device_used_str) where:
        - model_dict is suitable for passing to convert_pdf()
        - device_used_str is the actual device string used (e.g., "mps", "cuda", "cpu")

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

    # Determine the device to use
    device_str: str
    if device is not None:
        # Explicit device override
        device_str = device
    else:
        # Auto-detect best device
        from .device import detect_device  # noqa: PLC0415

        device_info = detect_device()
        device_str = str(device_info.device_type)
        logger.info("Using device: %s (%s)", device_info.device_type, device_info.device_name)

    logger.info("Loading Surya/Marker models on device: %s", device_str)
    try:
        import torch  # noqa: PLC0415

        model_dict = create_model_dict(device=torch.device(device_str))
    except Exception as exc:
        raise SuryaError(
            f"Failed to load Surya/Marker models: {exc}",
            details={"device": device_str, "requested_device": device},
        ) from exc

    logger.info("Surya/Marker models loaded successfully on %s.", device_str)
    return model_dict, device_str


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


def convert_pdf_with_fallback(
    input_path: Path,
    model_dict: dict[str, Any],
    config: SuryaConfig | None = None,
    page_range: list[int] | None = None,
    strict_gpu: bool = False,
) -> tuple[str, bool]:
    """Convert PDF with fallback from GPU to CPU on failure.

    If GPU inference fails (MPS/CUDA error, OOM), reloads models on CPU
    and retries the entire conversion. This handles known MPS bugs in
    the detection model.

    Args:
        input_path: Path to the input PDF file.
        model_dict: Pre-loaded model dictionary.
        config: Surya configuration.
        page_range: Optional list of page indices.
        strict_gpu: If True, don't fall back to CPU on failure.

    Returns:
        Tuple of (markdown_text, fallback_occurred).

    Raises:
        SuryaError: If conversion fails and strict_gpu=True, or if
                    CPU fallback also fails.
    """
    fallback_needed = False
    error_message = ""

    try:
        markdown = convert_pdf(input_path, model_dict, config, page_range)
        return markdown, False
    except RuntimeError as exc:
        if strict_gpu:
            raise SuryaError(
                f"GPU inference failed and strict_gpu=True: {exc}",
                filename=str(input_path),
                details={"strict_gpu": True, "error": str(exc)},
            ) from exc
        fallback_needed = True
        error_message = str(exc)

    # OOM recovery must happen OUTSIDE except block to allow GC
    if fallback_needed:
        # Clear GPU memory before CPU retry
        try:
            import torch  # noqa: PLC0415

            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass

        logger.warning(
            "GPU inference failed, retrying on CPU: %s",
            error_message,
        )
        cpu_model_dict, _ = load_models(device="cpu")
        markdown = convert_pdf(input_path, cpu_model_dict, config, page_range)
        return markdown, True

    # This should never be reached, but satisfy type checker
    raise SuryaError(
        "Unexpected state in convert_pdf_with_fallback",
        filename=str(input_path),
    )
