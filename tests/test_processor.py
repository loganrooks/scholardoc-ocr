"""Tests for PDFProcessor with context manager safety."""

from pathlib import Path

from scholardoc_ocr.processor import PDFProcessor


def test_extract_text(sample_pdf: Path):
    proc = PDFProcessor()
    text = proc.extract_text(sample_pdf)
    assert "test content" in text


def test_extract_text_by_page(sample_pdf: Path):
    proc = PDFProcessor()
    pages = proc.extract_text_by_page(sample_pdf)
    assert len(pages) == 2
    assert "page one" in pages[0]
    assert "page two" in pages[1]


def test_extract_pages(sample_pdf: Path, tmp_path: Path):
    proc = PDFProcessor()
    out = tmp_path / "extracted.pdf"
    result = proc.extract_pages(sample_pdf, [0], out)
    assert result is True
    assert proc.get_page_count(out) == 1
    text = proc.extract_text(out)
    assert "page one" in text


def test_get_page_count(sample_pdf: Path):
    proc = PDFProcessor()
    assert proc.get_page_count(sample_pdf) == 2


def test_extract_text_empty_pdf(empty_pdf: Path):
    proc = PDFProcessor()
    text = proc.extract_text(empty_pdf)
    assert text.strip() == ""


def test_replace_pages(sample_pdf: Path, tmp_path: Path):
    """Replace page 1 of sample_pdf with page 0 of a replacement PDF."""
    import fitz

    # Create replacement PDF
    replacement_path = tmp_path / "replacement.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Replaced content here.")
    doc.save(replacement_path)
    doc.close()

    proc = PDFProcessor()
    out = tmp_path / "merged.pdf"
    result = proc.replace_pages(sample_pdf, replacement_path, [1], out)
    assert result is True
    assert proc.get_page_count(out) == 2
    pages = proc.extract_text_by_page(out)
    assert "page one" in pages[0]
    assert "Replaced content" in pages[1]


def test_context_manager_cleanup(sample_pdf: Path):
    """Verify extract_text completes without resource warnings."""
    import warnings

    proc = PDFProcessor()
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        proc.extract_text(sample_pdf)
    resource_warnings = [x for x in w if issubclass(x.category, ResourceWarning)]
    assert len(resource_warnings) == 0
