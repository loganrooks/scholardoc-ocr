"""Batch configuration infrastructure for Surya batch sizing.

IMPORTANT: The Surya batch size environment variables (RECOGNITION_BATCH_SIZE,
DETECTOR_BATCH_SIZE) must be set BEFORE importing marker. Call
configure_surya_batch_sizes() early in the pipeline, before any marker/Surya
imports occur.

This module provides:
- Memory detection (system RAM for MPS, VRAM for CUDA)
- Hardware-aware batch size configuration
- FlaggedPage dataclass for tracking page origins in cross-file batching

All torch imports are lazy (inside function bodies) to avoid loading ML
dependencies at module import time.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

if TYPE_CHECKING:
    from .types import FileResult

logger = logging.getLogger(__name__)


@dataclass
class FlaggedPage:
    """Track origin of a flagged page for result mapping.

    When processing multiple PDFs in a batch, flagged pages from different files
    are combined into a single batch PDF for Surya processing. This dataclass
    tracks the origin of each page so results can be mapped back to the correct
    source file after processing.

    Attributes:
        file_result: Reference to the source file result.
        page_number: 0-indexed page number in the source PDF.
        input_path: Path to the source PDF file.
        batch_index: Position in the combined batch PDF (assigned during batching).
    """

    file_result: FileResult
    page_number: int
    input_path: Path
    batch_index: int = 0


def get_available_memory_gb(device: str | None = None) -> float:
    """Get available memory in gigabytes for the specified device.

    For CPU and MPS (Apple Silicon unified memory), returns total system RAM.
    For CUDA, returns GPU VRAM of device 0.

    Args:
        device: Device string ("cpu", "mps", "cuda") or None for system memory.

    Returns:
        Available memory in gigabytes as a float.

    Examples:
        >>> get_available_memory_gb()  # System memory
        32.0
        >>> get_available_memory_gb("cuda")  # GPU VRAM
        24.0
    """
    if device == "cuda":
        try:
            import torch  # noqa: PLC0415 (lazy import)

            if torch.cuda.is_available():
                props = torch.cuda.get_device_properties(0)
                return props.total_memory / (1024**3)
        except ImportError:
            logger.debug("torch not available for CUDA memory detection")
        except Exception as exc:
            logger.warning("Failed to get CUDA memory: %s", exc)

    # For CPU, MPS, or fallback: use system memory
    mem = psutil.virtual_memory()
    return mem.total / (1024**3)


def configure_surya_batch_sizes(
    device: str, available_memory_gb: float | None = None
) -> dict[str, str]:
    """Configure Surya batch sizes based on device and available memory.

    MUST be called before importing marker or any Surya modules, as the batch
    sizes are read from environment variables at import time.

    Uses os.environ.setdefault() to allow user overrides - if the environment
    variable is already set, it will NOT be overwritten.

    Batch size tiers (from research):
        - CPU: RECOGNITION=32, DETECTOR=6 (conservative)
        - GPU 8GB: RECOGNITION=32, DETECTOR=16
        - GPU 16GB: RECOGNITION=64, DETECTOR=32
        - GPU 32GB+: RECOGNITION=128, DETECTOR=64

    Args:
        device: Device string ("cpu", "mps", "cuda").
        available_memory_gb: Available memory in GB. If None, auto-detected.

    Returns:
        Dict mapping env var names to their values (the actual values set,
        which may differ from defaults if user overrides exist).

    Examples:
        >>> # Set batch sizes for 32GB Apple Silicon
        >>> env_vars = configure_surya_batch_sizes("mps", 32.0)
        >>> env_vars
        {'RECOGNITION_BATCH_SIZE': '128', 'DETECTOR_BATCH_SIZE': '64'}
    """
    if available_memory_gb is None:
        available_memory_gb = get_available_memory_gb(device)

    logger.debug(
        "Configuring batch sizes for device=%s, memory=%.1fGB", device, available_memory_gb
    )

    # Determine batch sizes based on device and memory
    if device == "cpu":
        # CPU: conservative defaults
        recognition_batch = "32"
        detector_batch = "6"
    elif available_memory_gb >= 32.0:
        # 32GB+: aggressive batching
        recognition_batch = "128"
        detector_batch = "64"
    elif available_memory_gb >= 16.0:
        # 16GB: moderate batching
        recognition_batch = "64"
        detector_batch = "32"
    else:
        # 8GB or less: conservative GPU batching
        recognition_batch = "32"
        detector_batch = "16"

    # Use setdefault to allow user overrides
    actual_recognition = os.environ.setdefault("RECOGNITION_BATCH_SIZE", recognition_batch)
    actual_detector = os.environ.setdefault("DETECTOR_BATCH_SIZE", detector_batch)

    result = {
        "RECOGNITION_BATCH_SIZE": actual_recognition,
        "DETECTOR_BATCH_SIZE": actual_detector,
    }

    logger.info(
        "Surya batch sizes configured: RECOGNITION=%s, DETECTOR=%s (device=%s, memory=%.1fGB)",
        actual_recognition,
        actual_detector,
        device,
        available_memory_gb,
    )

    return result
