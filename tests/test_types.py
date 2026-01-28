"""Tests for result types serialization and properties."""

import json

from scholardoc_ocr.types import (
    BatchResult,
    FileResult,
    OCREngine,
    PageResult,
    PageStatus,
)


def _make_page(page_number: int = 0, flagged: bool = False, text: str | None = None) -> PageResult:
    return PageResult(
        page_number=page_number,
        status=PageStatus.FLAGGED if flagged else PageStatus.GOOD,
        quality_score=0.5 if flagged else 0.95,
        engine=OCREngine.TESSERACT,
        flagged=flagged,
        text=text,
    )


def _make_file(filename: str = "test.pdf", success: bool = True, pages: list | None = None):
    pages = pages if pages is not None else [_make_page(0), _make_page(1)]
    return FileResult(
        filename=filename,
        success=success,
        engine=OCREngine.TESSERACT,
        quality_score=0.9,
        page_count=len(pages),
        pages=pages,
    )


def test_page_result_to_dict():
    page = _make_page(0, text="hello")
    d = page.to_dict()
    assert d["page_number"] == 0
    assert d["status"] == "good"
    assert d["engine"] == "tesseract"
    assert "text" not in d


def test_page_result_to_dict_with_text():
    page = _make_page(0, text="hello")
    d = page.to_dict(include_text=True)
    assert d["text"] == "hello"


def test_file_result_to_dict():
    fr = _make_file()
    d = fr.to_dict()
    assert d["filename"] == "test.pdf"
    assert len(d["pages"]) == 2
    assert d["pages"][0]["page_number"] == 0


def test_file_result_flagged_pages():
    pages = [_make_page(0, flagged=False), _make_page(1, flagged=True)]
    fr = _make_file(pages=pages)
    flagged = fr.flagged_pages
    assert len(flagged) == 1
    assert flagged[0].page_number == 1


def test_batch_result_to_json():
    br = BatchResult(files=[_make_file()], total_time_seconds=1.5)
    j = br.to_json()
    parsed = json.loads(j)
    assert parsed["total_time_seconds"] == 1.5
    assert len(parsed["files"]) == 1


def test_batch_result_counts():
    br = BatchResult(
        files=[
            _make_file("a.pdf", success=True, pages=[_make_page(0, flagged=True)]),
            _make_file("b.pdf", success=False),
            _make_file("c.pdf", success=True),
        ]
    )
    assert br.success_count == 2
    assert br.error_count == 1
    assert br.flagged_count == 1


def test_enum_serialization():
    page = _make_page(0)
    d = page.to_dict()
    assert isinstance(d["status"], str)
    assert isinstance(d["engine"], str)
    assert d["status"] == "good"
    assert d["engine"] == "tesseract"
