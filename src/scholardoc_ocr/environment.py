"""Environment validation and startup diagnostics for scholardoc-ocr.

Checks for required external dependencies (tesseract binary, language packs)
and system prerequisites (writable TMPDIR) before pipeline dispatch.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile

logger = logging.getLogger(__name__)


def check_gpu_availability() -> tuple[bool, str]:
    """Check GPU availability and return status message.

    Returns:
        Tuple of (available, message) where message explains the status.
        The message is actionable, explaining why GPU is or isn't available.
    """
    try:
        import torch
    except ImportError:
        return (False, "GPU not available (PyTorch not installed)")

    # Check CUDA first (highest priority)
    if torch.cuda.is_available():
        device_name = torch.cuda.get_device_name(0)
        return (True, f"CUDA available: {device_name}")

    # Check MPS (Apple Silicon)
    if hasattr(torch.backends, "mps"):
        if torch.backends.mps.is_available():
            return (True, "MPS available (Apple Silicon)")
        elif torch.backends.mps.is_built():
            return (False, "MPS built but not available (macOS < 12.3 or no GPU)")
        else:
            return (False, "MPS not available (PyTorch not built with MPS)")

    return (False, "GPU not available, will use CPU")


class EnvironmentError(RuntimeError):
    """Raised when required environment dependencies are missing or misconfigured."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        detail = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"Environment validation failed:\n{detail}")


def _get_tesseract_langs() -> list[str]:
    """Return list of available tesseract language packs."""
    result = subprocess.run(
        ["tesseract", "--list-langs"],
        capture_output=True,
        text=True,
    )
    # First line is "List of available languages (N):", rest are lang codes
    lines = result.stdout.strip().splitlines()
    return [line.strip() for line in lines[1:] if line.strip()]


def _get_tesseract_version() -> str:
    """Return tesseract version string."""
    result = subprocess.run(
        ["tesseract", "--version"],
        capture_output=True,
        text=True,
    )
    # Version info may be on stdout or stderr depending on platform
    output = result.stdout or result.stderr
    first_line = output.strip().splitlines()[0] if output.strip() else "unknown"
    return first_line


def validate_environment(langs_tesseract: str = "eng,fra,ell,lat,deu") -> None:
    """Validate that all required external dependencies are available.

    Checks tesseract binary, required language packs, and writable TMPDIR.
    Raises EnvironmentError with all detected problems if any checks fail.
    """
    problems: list[str] = []

    # Check tesseract binary
    tesseract_path = shutil.which("tesseract")
    if tesseract_path is None:
        problems.append(
            "tesseract not found on PATH. "
            "Install: brew install tesseract (macOS) or apt install tesseract-ocr (Linux)"
        )
    else:
        # Check language packs
        try:
            available = _get_tesseract_langs()
            required = [lang.strip() for lang in langs_tesseract.split(",")]
            for lang in required:
                if lang not in available:
                    problems.append(
                        f"tesseract language pack '{lang}' not installed. "
                        f"Install: brew install tesseract-lang (macOS) "
                        f"or apt install tesseract-ocr-{lang} (Linux)"
                    )
        except (subprocess.SubprocessError, OSError) as e:
            problems.append(f"Failed to query tesseract languages: {e}")

    # Check TMPDIR is writable
    tmp_dir = tempfile.gettempdir()
    try:
        fd, tmp_path = tempfile.mkstemp(dir=tmp_dir)
        os.close(fd)
        os.unlink(tmp_path)
    except OSError:
        problems.append(f"TMPDIR ({tmp_dir}) is not writable")

    if problems:
        raise EnvironmentError(problems)


def log_startup_diagnostics(langs_tesseract: str = "eng,fra,ell,lat,deu") -> None:
    """Log system and dependency information at INFO level for debugging.

    Does not raise on errors -- logs warnings for any issues but continues.
    """
    logger.info("Python version: %s", sys.version)
    logger.info("Platform: %s", platform.platform())
    logger.info("TMPDIR: %s", tempfile.gettempdir())
    logger.info("Requested languages: %s", langs_tesseract)

    tesseract_path = shutil.which("tesseract")
    if tesseract_path is None:
        logger.warning("tesseract not found on PATH")
        return

    try:
        version = _get_tesseract_version()
        logger.info("tesseract version: %s", version)
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning("Failed to get tesseract version: %s", e)

    try:
        available = _get_tesseract_langs()
        logger.info("tesseract available languages: %s", ", ".join(available))
    except (subprocess.SubprocessError, OSError) as e:
        logger.warning("Failed to get tesseract languages: %s", e)

    # GPU availability
    gpu_available, gpu_message = check_gpu_availability()
    logger.info("GPU: %s", gpu_message)
