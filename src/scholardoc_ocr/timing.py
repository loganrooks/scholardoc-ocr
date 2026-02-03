"""GPU-aware timing utilities for benchmarking on Apple Silicon.

Provides hardware detection and MPS-synchronized timing for accurate benchmarks.
All torch imports are lazy to avoid loading heavy ML dependencies at module import time.
"""

from __future__ import annotations

import platform
import subprocess
import time
from contextlib import contextmanager
from typing import TYPE_CHECKING, Generator

if TYPE_CHECKING:
    pass


def get_hardware_profile() -> str:
    """Detect Apple Silicon variant (M1/M2/M3/M4) or return 'cpu'.

    Uses sysctl on macOS to get the CPU brand string and extracts
    the Apple Silicon generation.

    Returns:
        One of "M1", "M2", "M3", "M4", or "cpu" for other platforms/architectures.
    """
    if platform.system() != "Darwin":
        return "cpu"

    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        brand = result.stdout.strip()

        # Apple Silicon brand strings look like "Apple M1 Pro", "Apple M2 Max", etc.
        for variant in ("M4", "M3", "M2", "M1"):
            if variant in brand:
                return variant

        # Non-Apple Silicon Mac (Intel)
        return "cpu"
    except (subprocess.SubprocessError, OSError):
        return "cpu"


def mps_available() -> bool:
    """Check if MPS (Metal Performance Shaders) backend is available.

    Returns:
        True if torch MPS backend is available, False otherwise.
    """
    try:
        import torch  # noqa: PLC0415

        return torch.backends.mps.is_available()
    except ImportError:
        return False


def mps_sync() -> None:
    """Synchronize MPS operations if MPS is available.

    This ensures all MPS operations are complete before timing measurements.
    No-op if MPS is not available.
    """
    if mps_available():
        import torch  # noqa: PLC0415

        torch.mps.synchronize()


@contextmanager
def mps_timed(name: str) -> Generator[dict, None, None]:
    """Context manager for MPS-synchronized timing measurements.

    Yields a dict that will be populated with timing results after the
    context exits. Synchronizes MPS operations before taking the final
    timing measurement.

    Args:
        name: Label for the timing measurement (for logging/debugging).

    Yields:
        A dict that will contain {"elapsed": float, "name": str} after exit.

    Example:
        with mps_timed("model_inference") as timing:
            result = model(input)
        print(f"{timing['name']} took {timing['elapsed']:.3f}s")
    """
    result: dict = {"name": name, "elapsed": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        # Synchronize MPS before measuring to ensure GPU work is complete
        mps_sync()
        result["elapsed"] = time.perf_counter() - start
