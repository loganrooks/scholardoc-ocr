"""Shared test fixtures for scholardoc-ocr tests."""

from pathlib import Path

import pytest


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    """Create a minimal valid PDF for testing."""
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "This is test content on page one.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "This is test content on page two.")
    pdf_path = tmp_path / "test.pdf"
    doc.save(pdf_path)
    doc.close()
    return pdf_path


@pytest.fixture
def empty_pdf(tmp_path: Path) -> Path:
    """Create a PDF with no text content."""
    import fitz

    doc = fitz.open()
    doc.new_page()
    pdf_path = tmp_path / "empty.pdf"
    doc.save(pdf_path)
    doc.close()
    return pdf_path
