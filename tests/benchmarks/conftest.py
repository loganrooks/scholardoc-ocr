"""Benchmark test fixtures for scholardoc-ocr performance testing.

Provides session-scoped fixtures for hardware detection, model loading,
and sample PDF generation. Also registers memray markers for memory testing.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from scholardoc_ocr.timing import get_hardware_profile, mps_sync

if TYPE_CHECKING:
    pass


def pytest_configure(config: pytest.Config) -> None:
    """Register memray markers for memory limit testing."""
    config.addinivalue_line(
        "markers",
        "limit_memory(memory_limit): Set memory limit for the test (memray)",
    )
    config.addinivalue_line(
        "markers",
        "limit_leaks(locations, filter_fn): Set memory leak detection parameters (memray)",
    )


@pytest.fixture(scope="session")
def hardware_profile() -> str:
    """Return the hardware profile string for the current machine.

    Returns:
        One of "M1", "M2", "M3", "M4" for Apple Silicon, or "cpu" otherwise.
    """
    profile = get_hardware_profile()
    return profile


@pytest.fixture(scope="session")
def loaded_models() -> dict[str, Any] | None:
    """Load Surya/Marker models once per session for benchmark reuse.

    This fixture lazily loads models on first use and keeps them loaded
    for the entire test session. Includes MPS synchronization after load.

    Returns:
        Model dictionary from surya.load_models(), or None if marker not installed.
    """
    try:
        from scholardoc_ocr import surya
    except ImportError:
        pytest.skip("marker-pdf not installed")
        return None

    if not surya.is_available():
        pytest.skip("marker-pdf not installed")
        return None

    model_dict = surya.load_models()
    # Ensure models are fully loaded on MPS before returning
    mps_sync()
    return model_dict


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a minimal 1-page PDF with text for benchmarking.

    Uses PyMuPDF (fitz) to programmatically create a PDF with
    sample text suitable for OCR testing.

    Args:
        tmp_path: pytest temporary directory fixture.

    Returns:
        Path to the generated PDF file.
    """
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)  # US Letter size

    # Add sample text that exercises OCR
    text_content = """
    The Philosophy of Mind

    This is a sample academic text for OCR benchmarking purposes.
    It contains multiple paragraphs with various character types.

    Section 1: Introduction

    The study of consciousness has been central to philosophical inquiry
    since Descartes' famous cogito ergo sum. Modern philosophers like
    Husserl, Heidegger, and Sartre continued this phenomenological tradition.

    Section 2: Key Terms

    - Phenomenology: the study of structures of experience
    - Intentionality: the aboutness of mental states
    - Qualia: subjective conscious experiences

    References: Kant (1781), Hegel (1807), Nietzsche (1886).
    """

    # Insert text with a readable font
    text_rect = fitz.Rect(72, 72, 540, 720)  # 1-inch margins
    page.insert_textbox(
        text_rect,
        text_content,
        fontsize=11,
        fontname="helv",
    )

    pdf_path = tmp_path / "benchmark_sample.pdf"
    doc.save(pdf_path)
    doc.close()

    return pdf_path


@pytest.fixture
def multi_page_pdf(tmp_path: Path) -> Path:
    """Create a multi-page PDF for batch processing benchmarks.

    Generates a 5-page PDF with varied content on each page.

    Args:
        tmp_path: pytest temporary directory fixture.

    Returns:
        Path to the generated PDF file.
    """
    import fitz

    doc = fitz.open()
    pages_content = [
        "Page 1: Introduction to Epistemology\n\nKnowledge is justified true belief.",
        "Page 2: Metaphysics\n\nWhat is the nature of reality? Being qua being.",
        "Page 3: Ethics\n\nThe categorical imperative: act only according to that maxim.",
        "Page 4: Aesthetics\n\nThe beautiful is that which pleases universally without concept.",
        "Page 5: Logic\n\nAll men are mortal. Socrates is a man. Therefore, Socrates is mortal.",
    ]

    for content in pages_content:
        page = doc.new_page(width=612, height=792)
        text_rect = fitz.Rect(72, 72, 540, 720)
        page.insert_textbox(text_rect, content, fontsize=12, fontname="helv")

    pdf_path = tmp_path / "benchmark_multipage.pdf"
    doc.save(pdf_path)
    doc.close()

    return pdf_path
