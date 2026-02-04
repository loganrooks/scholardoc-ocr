"""Device detection and validation for GPU-accelerated OCR.

Provides hardware detection following CUDA > MPS > CPU priority with validation
to ensure the selected device actually works. All torch imports are lazy to avoid
loading heavy ML dependencies at module import time.

Typical usage:
    device_info = detect_device()
    print(f"Using {device_info.device_type}: {device_info.device_name}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class DeviceType(StrEnum):
    """Compute device types supported by the pipeline."""

    CUDA = "cuda"
    MPS = "mps"
    CPU = "cpu"


@dataclass
class DeviceInfo:
    """Information about the selected compute device.

    Attributes:
        device_type: The type of device (cuda, mps, or cpu).
        device_name: Human-readable device name (e.g., "NVIDIA A100", "Apple Silicon").
        validated: Whether the device was validated with a test tensor allocation.
        fallback_from: If we fell back from a higher-priority device, which one.
    """

    device_type: DeviceType
    device_name: str
    validated: bool = False
    fallback_from: DeviceType | None = field(default=None)


def _validate_device(device_str: str) -> bool:
    """Validate device by allocating a test tensor.

    Args:
        device_str: Device string to validate ("cuda", "mps", or "cpu").

    Returns:
        True if validation succeeded, False otherwise.
    """
    import torch  # noqa: PLC0415 (lazy import)

    try:
        _ = torch.zeros(1, device=device_str)
        return True
    except RuntimeError as e:
        logger.warning("Device %s validation failed: %s", device_str, e)
        return False


def _try_cuda() -> DeviceInfo | None:
    """Try to use CUDA device.

    Returns:
        DeviceInfo if CUDA is available and validated, None otherwise.
    """
    import torch  # noqa: PLC0415 (lazy import)

    if not torch.cuda.is_available():
        return None

    if _validate_device("cuda"):
        name = torch.cuda.get_device_name(0)
        logger.info("Using device: cuda (%s)", name)
        return DeviceInfo(
            device_type=DeviceType.CUDA,
            device_name=name,
            validated=True,
        )

    return None


def _try_mps() -> DeviceInfo | None:
    """Try to use MPS device (Apple Silicon).

    Returns:
        DeviceInfo if MPS is available and validated, None otherwise.
    """
    import torch  # noqa: PLC0415 (lazy import)

    # Check both is_built() and is_available() for comprehensive MPS detection
    if not torch.backends.mps.is_built():
        logger.debug("MPS not available: PyTorch not built with MPS support")
        return None

    if not torch.backends.mps.is_available():
        logger.debug("MPS not available: macOS version < 12.3 or no MPS device")
        return None

    if _validate_device("mps"):
        logger.info("Using device: mps (Apple Silicon)")
        return DeviceInfo(
            device_type=DeviceType.MPS,
            device_name="Apple Silicon",
            validated=True,
        )

    return None


def detect_device() -> DeviceInfo:
    """Detect the best available compute device.

    Checks devices in priority order: CUDA > MPS > CPU. Each device is validated
    by allocating a small test tensor. If validation fails, the next device in
    priority order is tried.

    Returns:
        DeviceInfo with the best available device, marked as validated.
        If a fallback occurred, fallback_from indicates the original device type.

    Examples:
        >>> device_info = detect_device()
        >>> print(device_info.device_type)
        mps  # On Apple Silicon
        >>> print(device_info.validated)
        True
    """
    fallback_from: DeviceType | None = None

    # Try CUDA first (highest priority)
    cuda_result = _try_cuda()
    if cuda_result is not None:
        return cuda_result

    # CUDA was tried but failed, track potential fallback
    import torch  # noqa: PLC0415 (lazy import)

    if torch.cuda.is_available():
        fallback_from = DeviceType.CUDA

    # Try MPS second (Apple Silicon)
    mps_result = _try_mps()
    if mps_result is not None:
        if fallback_from is not None:
            mps_result.fallback_from = fallback_from
        return mps_result

    # MPS was tried but failed, track fallback
    if fallback_from is None and torch.backends.mps.is_available():
        fallback_from = DeviceType.MPS

    # Fallback to CPU (always works)
    logger.info("Using device: cpu")
    return DeviceInfo(
        device_type=DeviceType.CPU,
        device_name="cpu",
        validated=True,
        fallback_from=fallback_from,
    )
