"""Batch configuration infrastructure for Surya batch sizing.

IMPORTANT: The Surya batch size environment variables (RECOGNITION_BATCH_SIZE,
DETECTOR_BATCH_SIZE) must be set BEFORE importing marker. Call
configure_surya_batch_sizes() early in the pipeline, before any marker/Surya
imports occur.

This module provides:
- Memory detection (system RAM for MPS, VRAM for CUDA)
- Hardware-aware batch size configuration
- FlaggedPage dataclass for tracking page origins in cross-file batching
- Cross-file batching functions for aggregating flagged pages

All torch imports are lazy (inside function bodies) to avoid loading ML
dependencies at module import time.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import fitz
import psutil

from .types import OCREngine, PageStatus

if TYPE_CHECKING:
    from .quality import QualityAnalyzer
    from .types import FileResult

logger = logging.getLogger(__name__)

# Memory estimate per page during Surya processing (detection + recognition + layout).
# Based on empirical testing: ~700MB peak per page on GPU.
# This is conservative to prevent system freezes on memory-constrained systems.
BATCH_SIZE_MEMORY_PER_PAGE_GB = 0.7

# Memory threshold below which the system is considered constrained.
# 4GB allows headroom for OS and other processes on 8GB machines.
MEMORY_PRESSURE_THRESHOLD_GB = 4.0


def check_memory_pressure() -> tuple[bool, float]:
    """Check if system is under memory pressure.

    Uses available (not total) memory to account for current system load.
    This is important for detecting pressure when other applications are running.

    Returns:
        Tuple of (is_constrained, available_gb).
        is_constrained is True if available memory < 4GB.

    Examples:
        >>> is_constrained, available = check_memory_pressure()
        >>> if is_constrained:
        ...     print(f"Low memory: {available:.1f}GB available")
    """
    mem = psutil.virtual_memory()
    available_gb = mem.available / (1024**3)
    is_constrained = available_gb < MEMORY_PRESSURE_THRESHOLD_GB
    return is_constrained, available_gb


def compute_safe_batch_size(
    total_pages: int,
    available_memory_gb: float,
    device: str,
) -> int:
    """Compute safe batch size based on available memory.

    Uses conservative memory estimates to prevent system freezes on
    memory-constrained systems (especially 8GB MPS machines where GPU
    memory pressure can freeze the system without Python OOM errors).

    Args:
        total_pages: Number of pages to process.
        available_memory_gb: Available system memory in GB.
        device: Device type ("mps", "cuda", "cpu").

    Returns:
        Recommended batch size (clamped to 1-100 range).

    Examples:
        >>> compute_safe_batch_size(50, 8.0, "mps")
        5  # 8GB * 0.5 / 0.7 = ~5 pages
        >>> compute_safe_batch_size(50, 32.0, "mps")
        22  # 32GB * 0.5 / 0.7 = ~22 pages
        >>> compute_safe_batch_size(50, 16.0, "cpu")
        32  # CPU capped at 32
    """
    if total_pages <= 0:
        return 0

    if device == "cpu":
        # CPU is more memory-efficient but slower, cap at 32
        return min(total_pages, 32)

    # GPU (MPS/CUDA): use 50% of available memory for safety margin
    # This leaves room for OS, other processes, and memory fragmentation
    safe_memory = available_memory_gb * 0.5
    max_by_memory = int(safe_memory / BATCH_SIZE_MEMORY_PER_PAGE_GB)

    # Clamp to reasonable range: minimum 1, maximum 100 or total_pages
    return max(1, min(total_pages, max_by_memory, 100))


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


def collect_flagged_pages(
    file_results: list[FileResult], input_paths: dict[str, Path]
) -> list[FlaggedPage]:
    """Aggregate flagged pages from all file results for cross-file batching.

    Collects all flagged pages from multiple file results into a single list,
    assigning sequential batch indices for combined PDF creation.

    Args:
        file_results: List of FileResult objects containing flagged pages.
        input_paths: Mapping from filename to input Path.

    Returns:
        List of FlaggedPage objects ordered for combined PDF creation,
        with batch_index assigned sequentially (0, 1, 2, ...).

    Examples:
        >>> file_results = [fr1, fr2]  # 3 flagged pages each
        >>> input_paths = {"doc1.pdf": Path("doc1.pdf"), "doc2.pdf": Path("doc2.pdf")}
        >>> pages = collect_flagged_pages(file_results, input_paths)
        >>> len(pages)
        6
        >>> [p.batch_index for p in pages]
        [0, 1, 2, 3, 4, 5]
    """
    pages: list[FlaggedPage] = []
    for fr in file_results:
        input_path = input_paths.get(fr.filename)
        if input_path is None:
            logger.warning("No input path for %s, skipping flagged pages", fr.filename)
            continue

        for page in fr.flagged_pages:
            pages.append(
                FlaggedPage(
                    file_result=fr,
                    page_number=page.page_number,
                    input_path=input_path,
                    batch_index=len(pages),
                )
            )

    logger.debug("Collected %d flagged pages from %d files", len(pages), len(file_results))
    return pages


def create_combined_pdf(flagged_pages: list[FlaggedPage], output_path: Path) -> None:
    """Create a combined PDF containing all flagged pages for batch processing.

    Extracts individual pages from source PDFs and combines them into a single
    PDF file, maintaining the order specified by batch_index.

    Args:
        flagged_pages: List of FlaggedPage objects to combine.
        output_path: Path where the combined PDF will be saved.

    Note:
        The combined PDF page order matches the batch_index order exactly.
        This is critical for mapping Surya results back to source files.

    Examples:
        >>> pages = [FlaggedPage(..., batch_index=0), FlaggedPage(..., batch_index=1)]
        >>> create_combined_pdf(pages, Path("/tmp/combined.pdf"))
        >>> # Combined PDF has 2 pages in batch_index order
    """
    if not flagged_pages:
        logger.warning("No flagged pages to combine, skipping PDF creation")
        return

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result_doc = fitz.open()

    # Sort by batch_index to ensure correct order
    sorted_pages = sorted(flagged_pages, key=lambda p: p.batch_index)

    for page in sorted_pages:
        try:
            with fitz.open(page.input_path) as source:
                result_doc.insert_pdf(
                    source,
                    from_page=page.page_number,
                    to_page=page.page_number,
                )
        except Exception as exc:
            logger.error(
                "Failed to extract page %d from %s: %s",
                page.page_number,
                page.input_path,
                exc,
            )
            raise

    result_doc.save(output_path)
    result_doc.close()
    logger.debug("Created combined PDF with %d pages at %s", len(flagged_pages), output_path)


def split_markdown_by_pages(markdown: str, page_count: int) -> list[str]:
    """Split Surya markdown output into per-page text.

    Uses heuristics to split Marker's markdown output since it doesn't provide
    explicit page markers. Tries horizontal rules first, then triple newlines,
    falling back to assigning all text to the first page.

    Args:
        markdown: The full markdown text from Surya/Marker.
        page_count: Expected number of pages.

    Returns:
        List of exactly page_count strings, one per page.
        Some may be empty if splitting produces fewer parts than pages.

    Examples:
        >>> split_markdown_by_pages("page1\\n---\\npage2", 2)
        ['page1', 'page2']
        >>> split_markdown_by_pages("no separators", 3)
        ['no separators', '', '']
    """
    if page_count == 0:
        return []
    if page_count == 1:
        return [markdown]

    # Try horizontal rule splits first (Marker often inserts these)
    parts = re.split(r"\n-{3,}\n", markdown)
    if len(parts) >= page_count:
        return parts[:page_count]

    # Try triple newline splits (page break heuristic)
    parts = re.split(r"\n{3,}", markdown)
    if len(parts) >= page_count:
        return parts[:page_count]

    # Fallback: first page gets all text, rest empty
    result = [markdown] + [""] * (page_count - 1)
    return result


def map_results_to_files(
    flagged_pages: list[FlaggedPage],
    surya_text: str,
    analyzer: QualityAnalyzer,
) -> None:
    """Map Surya batch results back to source file results.

    Splits the combined Surya output and updates each source FileResult's
    PageResult with the corresponding text, quality score, and engine.

    Args:
        flagged_pages: List of FlaggedPage objects (with batch_index).
        surya_text: Combined markdown output from Surya.
        analyzer: QualityAnalyzer for scoring the text.

    Note:
        This function mutates the file_result.pages in place. After calling,
        each flagged page will have:
        - text: The per-page text from Surya
        - engine: OCREngine.SURYA
        - quality_score: Score from analyzer
        - flagged: True if score < threshold
        - status: GOOD or FLAGGED based on score

    Examples:
        >>> map_results_to_files(flagged_pages, surya_markdown, analyzer)
        >>> # flagged_pages[0].file_result.pages[N] now has Surya text
    """
    page_texts = split_markdown_by_pages(surya_text, len(flagged_pages))

    for fp in flagged_pages:
        text = page_texts[fp.batch_index]
        result = analyzer.analyze(text)

        # Update the PageResult in the source FileResult
        page_result = fp.file_result.pages[fp.page_number]
        page_result.text = text
        page_result.engine = OCREngine.SURYA
        page_result.quality_score = result.score
        page_result.flagged = result.score < analyzer.threshold
        page_result.status = PageStatus.GOOD if not page_result.flagged else PageStatus.FLAGGED

    logger.debug("Mapped %d Surya results back to source files", len(flagged_pages))
