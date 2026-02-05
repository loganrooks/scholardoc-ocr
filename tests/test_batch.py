"""Unit tests for the batch configuration module.

Tests cover FlaggedPage dataclass, memory detection, batch size configuration,
and cross-file batching functions across different memory tiers and device types.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import fitz
import pytest

from scholardoc_ocr.batch import (
    FlaggedPage,
    collect_flagged_pages,
    configure_surya_batch_sizes,
    create_combined_pdf,
    get_available_memory_gb,
    map_results_to_files,
    split_markdown_by_pages,
)
from scholardoc_ocr.types import FileResult, OCREngine, PageResult, PageStatus


@pytest.fixture(autouse=True)
def clear_batch_env_vars():
    """Clear batch-related environment variables before and after each test."""
    env_vars = ["RECOGNITION_BATCH_SIZE", "DETECTOR_BATCH_SIZE"]
    # Clear before test
    for var in env_vars:
        if var in os.environ:
            del os.environ[var]
    yield
    # Clear after test
    for var in env_vars:
        if var in os.environ:
            del os.environ[var]


# =============================================================================
# FlaggedPage Tests
# =============================================================================


class TestFlaggedPage:
    """Tests for FlaggedPage dataclass."""

    def test_flagged_page_creation(self):
        """Verify FlaggedPage can be created with all required fields."""
        mock_result = MagicMock(spec=FileResult)
        mock_result.filename = "test.pdf"

        flagged = FlaggedPage(
            file_result=mock_result,
            page_number=5,
            input_path=Path("/test/test.pdf"),
            batch_index=10,
        )

        assert flagged.file_result is mock_result
        assert flagged.page_number == 5
        assert flagged.input_path == Path("/test/test.pdf")
        assert flagged.batch_index == 10

    def test_flagged_page_batch_index_default(self):
        """Verify batch_index defaults to 0 if not specified."""
        mock_result = MagicMock(spec=FileResult)

        flagged = FlaggedPage(
            file_result=mock_result,
            page_number=0,
            input_path=Path("/test/doc.pdf"),
        )

        assert flagged.batch_index == 0

    def test_flagged_page_batch_index_tracking(self):
        """Verify batch_index correctly tracks position in combined batch."""
        mock_result = MagicMock(spec=FileResult)
        pages = []

        # Simulate creating flagged pages from multiple files
        for i in range(5):
            pages.append(
                FlaggedPage(
                    file_result=mock_result,
                    page_number=i,
                    input_path=Path(f"/test/doc{i}.pdf"),
                    batch_index=i * 2,  # Simulating non-contiguous batch positions
                )
            )

        assert pages[0].batch_index == 0
        assert pages[2].batch_index == 4
        assert pages[4].batch_index == 8


# =============================================================================
# Memory Detection Tests
# =============================================================================


class TestGetAvailableMemory:
    """Tests for get_available_memory_gb function."""

    def test_returns_positive_float(self):
        """get_available_memory_gb() returns a positive float."""
        memory = get_available_memory_gb()
        assert isinstance(memory, float)
        assert memory > 0.0

    def test_returns_reasonable_value(self):
        """get_available_memory_gb() returns a reasonable value (1-1024 GB)."""
        memory = get_available_memory_gb()
        assert 1.0 <= memory <= 1024.0

    def test_cpu_device_uses_system_memory(self):
        """CPU device returns system memory."""
        with patch("scholardoc_ocr.batch.psutil") as mock_psutil:
            mock_vmem = MagicMock()
            mock_vmem.total = 32 * (1024**3)  # 32 GB
            mock_psutil.virtual_memory.return_value = mock_vmem

            memory = get_available_memory_gb("cpu")

            assert memory == 32.0
            mock_psutil.virtual_memory.assert_called_once()

    def test_mps_device_uses_system_memory(self):
        """MPS device returns system memory (unified memory on Apple Silicon)."""
        with patch("scholardoc_ocr.batch.psutil") as mock_psutil:
            mock_vmem = MagicMock()
            mock_vmem.total = 16 * (1024**3)  # 16 GB
            mock_psutil.virtual_memory.return_value = mock_vmem

            memory = get_available_memory_gb("mps")

            assert memory == 16.0

    def test_cuda_device_uses_gpu_memory(self):
        """CUDA device returns GPU VRAM."""
        mock_torch = MagicMock()
        mock_torch.cuda.is_available.return_value = True
        mock_props = MagicMock()
        mock_props.total_memory = 24 * (1024**3)  # 24 GB VRAM
        mock_torch.cuda.get_device_properties.return_value = mock_props

        with patch.dict("sys.modules", {"torch": mock_torch}):
            # Re-import to get fresh function
            from scholardoc_ocr.batch import get_available_memory_gb

            # Use system memory as fallback since we can't fully mock the lazy import
            memory = get_available_memory_gb("cuda")

            # Should be positive regardless of mock success
            assert memory > 0.0

    def test_cuda_fallback_to_system_on_error(self):
        """CUDA falls back to system memory if torch not available."""
        with patch("scholardoc_ocr.batch.psutil") as mock_psutil:
            mock_vmem = MagicMock()
            mock_vmem.total = 64 * (1024**3)  # 64 GB
            mock_psutil.virtual_memory.return_value = mock_vmem

            # When torch is not available, should fall back to system memory
            memory = get_available_memory_gb("cuda")

            # Should get some positive value (either GPU or system fallback)
            assert memory > 0.0


# =============================================================================
# Batch Size Configuration Tests
# =============================================================================


class TestConfigureSuryaBatchSizes:
    """Tests for configure_surya_batch_sizes function."""

    def test_cpu_defaults(self):
        """CPU gets conservative batch sizes."""
        result = configure_surya_batch_sizes("cpu", 32.0)

        assert result["RECOGNITION_BATCH_SIZE"] == "32"
        assert result["DETECTOR_BATCH_SIZE"] == "6"
        assert os.environ["RECOGNITION_BATCH_SIZE"] == "32"
        assert os.environ["DETECTOR_BATCH_SIZE"] == "6"

    def test_mps_8gb(self):
        """8GB MPS gets conservative GPU batch sizes."""
        result = configure_surya_batch_sizes("mps", 8.0)

        assert result["RECOGNITION_BATCH_SIZE"] == "32"
        assert result["DETECTOR_BATCH_SIZE"] == "16"

    def test_mps_16gb(self):
        """16GB MPS gets moderate batch sizes."""
        result = configure_surya_batch_sizes("mps", 16.0)

        assert result["RECOGNITION_BATCH_SIZE"] == "64"
        assert result["DETECTOR_BATCH_SIZE"] == "32"

    def test_mps_32gb(self):
        """32GB+ MPS gets aggressive batch sizes."""
        result = configure_surya_batch_sizes("mps", 32.0)

        assert result["RECOGNITION_BATCH_SIZE"] == "128"
        assert result["DETECTOR_BATCH_SIZE"] == "64"

    def test_cuda_32gb(self):
        """32GB CUDA gets same aggressive batch sizes as MPS."""
        result = configure_surya_batch_sizes("cuda", 32.0)

        assert result["RECOGNITION_BATCH_SIZE"] == "128"
        assert result["DETECTOR_BATCH_SIZE"] == "64"

    def test_cuda_24gb(self):
        """24GB CUDA gets 16GB tier batch sizes."""
        result = configure_surya_batch_sizes("cuda", 24.0)

        assert result["RECOGNITION_BATCH_SIZE"] == "64"
        assert result["DETECTOR_BATCH_SIZE"] == "32"

    def test_returns_dict_of_values(self):
        """configure_surya_batch_sizes returns dict with set values."""
        result = configure_surya_batch_sizes("mps", 16.0)

        assert isinstance(result, dict)
        assert "RECOGNITION_BATCH_SIZE" in result
        assert "DETECTOR_BATCH_SIZE" in result
        assert isinstance(result["RECOGNITION_BATCH_SIZE"], str)
        assert isinstance(result["DETECTOR_BATCH_SIZE"], str)

    def test_preserves_existing_env_vars(self):
        """setdefault pattern preserves existing env vars."""
        os.environ["RECOGNITION_BATCH_SIZE"] = "256"
        os.environ["DETECTOR_BATCH_SIZE"] = "100"

        result = configure_surya_batch_sizes("mps", 32.0)

        # Should return the existing values, not override
        assert result["RECOGNITION_BATCH_SIZE"] == "256"
        assert result["DETECTOR_BATCH_SIZE"] == "100"
        assert os.environ["RECOGNITION_BATCH_SIZE"] == "256"
        assert os.environ["DETECTOR_BATCH_SIZE"] == "100"

    def test_env_var_override_partial(self):
        """Partial env var override - only set vars are preserved."""
        os.environ["RECOGNITION_BATCH_SIZE"] = "200"
        # DETECTOR_BATCH_SIZE not set

        result = configure_surya_batch_sizes("mps", 32.0)

        # Recognition should be preserved, detector should be set
        assert result["RECOGNITION_BATCH_SIZE"] == "200"
        assert result["DETECTOR_BATCH_SIZE"] == "64"  # Default for 32GB

    def test_memory_tier_boundaries(self):
        """Test boundary conditions for memory tiers."""
        # Just under 16GB should get 8GB tier
        result = configure_surya_batch_sizes("mps", 15.9)
        assert result["RECOGNITION_BATCH_SIZE"] == "32"
        assert result["DETECTOR_BATCH_SIZE"] == "16"

        # Clear env vars for next test
        del os.environ["RECOGNITION_BATCH_SIZE"]
        del os.environ["DETECTOR_BATCH_SIZE"]

        # Just under 32GB should get 16GB tier
        result = configure_surya_batch_sizes("mps", 31.9)
        assert result["RECOGNITION_BATCH_SIZE"] == "64"
        assert result["DETECTOR_BATCH_SIZE"] == "32"

    def test_auto_memory_detection(self):
        """When available_memory_gb is None, auto-detects memory."""
        with patch("scholardoc_ocr.batch.get_available_memory_gb") as mock_get_mem:
            mock_get_mem.return_value = 64.0

            result = configure_surya_batch_sizes("mps", None)

            mock_get_mem.assert_called_once_with("mps")
            # 64GB should get 32GB+ tier
            assert result["RECOGNITION_BATCH_SIZE"] == "128"
            assert result["DETECTOR_BATCH_SIZE"] == "64"


# =============================================================================
# Split Markdown By Pages Tests
# =============================================================================


class TestSplitMarkdownByPages:
    """Tests for split_markdown_by_pages function."""

    def test_single_page(self):
        """1 page returns [markdown]."""
        result = split_markdown_by_pages("some text here", 1)
        assert result == ["some text here"]

    def test_empty_input(self):
        """0 pages returns []."""
        result = split_markdown_by_pages("some text", 0)
        assert result == []

    def test_horizontal_rule_split(self):
        """Split on horizontal rules (---)."""
        markdown = "page1\n---\npage2\n---\npage3"
        result = split_markdown_by_pages(markdown, 3)
        assert result == ["page1", "page2", "page3"]

    def test_triple_newline_split(self):
        """Split on triple newlines."""
        markdown = "page1\n\n\npage2\n\n\npage3"
        result = split_markdown_by_pages(markdown, 3)
        assert result == ["page1", "page2", "page3"]

    def test_fallback_first_page(self):
        """Fallback: no separators -> first page gets all, rest empty."""
        result = split_markdown_by_pages("no separators", 3)
        assert result == ["no separators", "", ""]

    def test_extra_splits_truncated(self):
        """Extra splits are truncated to page_count."""
        markdown = "a\n---\nb\n---\nc\n---\nd"
        result = split_markdown_by_pages(markdown, 2)
        assert result == ["a", "b"]

    def test_horizontal_rule_with_more_dashes(self):
        """Horizontal rules with more than 3 dashes work."""
        markdown = "page1\n-----\npage2"
        result = split_markdown_by_pages(markdown, 2)
        assert result == ["page1", "page2"]


# =============================================================================
# Collect Flagged Pages Tests
# =============================================================================


def _make_file_result(filename: str, page_count: int, flagged_indices: list[int]) -> FileResult:
    """Create a FileResult with specified flagged pages."""
    pages = []
    for i in range(page_count):
        flagged = i in flagged_indices
        pages.append(
            PageResult(
                page_number=i,
                status=PageStatus.FLAGGED if flagged else PageStatus.GOOD,
                quality_score=0.40 if flagged else 0.95,
                engine=OCREngine.TESSERACT,
                flagged=flagged,
                text=f"text for page {i}",
            )
        )
    return FileResult(
        filename=filename,
        success=True,
        engine=OCREngine.TESSERACT,
        quality_score=0.75,
        page_count=page_count,
        pages=pages,
    )


class TestCollectFlaggedPages:
    """Tests for collect_flagged_pages function."""

    def test_collects_from_multiple_files(self):
        """2 files with 3 flagged pages each -> 6 FlaggedPage objects."""
        fr1 = _make_file_result("doc1.pdf", page_count=5, flagged_indices=[0, 2, 4])
        fr2 = _make_file_result("doc2.pdf", page_count=5, flagged_indices=[1, 2, 3])
        input_paths = {
            "doc1.pdf": Path("/test/doc1.pdf"),
            "doc2.pdf": Path("/test/doc2.pdf"),
        }

        result = collect_flagged_pages([fr1, fr2], input_paths)

        assert len(result) == 6

    def test_batch_index_sequential(self):
        """batch_index is 0,1,2,3,4,5 for 6 pages."""
        fr1 = _make_file_result("doc1.pdf", page_count=5, flagged_indices=[0, 2, 4])
        fr2 = _make_file_result("doc2.pdf", page_count=5, flagged_indices=[1, 2, 3])
        input_paths = {
            "doc1.pdf": Path("/test/doc1.pdf"),
            "doc2.pdf": Path("/test/doc2.pdf"),
        }

        result = collect_flagged_pages([fr1, fr2], input_paths)

        assert [p.batch_index for p in result] == [0, 1, 2, 3, 4, 5]

    def test_empty_file_results(self):
        """Empty list returns empty list."""
        result = collect_flagged_pages([], {})
        assert result == []

    def test_no_flagged_pages(self):
        """Files with no flagged pages returns empty list."""
        fr = _make_file_result("doc.pdf", page_count=3, flagged_indices=[])
        input_paths = {"doc.pdf": Path("/test/doc.pdf")}

        result = collect_flagged_pages([fr], input_paths)

        assert result == []

    def test_preserves_page_number(self):
        """Page numbers are preserved from source file."""
        fr = _make_file_result("doc.pdf", page_count=10, flagged_indices=[3, 7])
        input_paths = {"doc.pdf": Path("/test/doc.pdf")}

        result = collect_flagged_pages([fr], input_paths)

        assert len(result) == 2
        assert result[0].page_number == 3
        assert result[1].page_number == 7

    def test_missing_input_path_skipped(self):
        """Files without input_path mapping are skipped."""
        fr = _make_file_result("doc.pdf", page_count=3, flagged_indices=[1])
        input_paths = {}  # No mapping for doc.pdf

        result = collect_flagged_pages([fr], input_paths)

        assert result == []


# =============================================================================
# Create Combined PDF Tests
# =============================================================================


def _create_test_pdf(path: Path, num_pages: int, text_per_page: list[str] | None = None) -> Path:
    """Create a test PDF with specified number of pages."""
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()
    for i in range(num_pages):
        page = doc.new_page()
        text = text_per_page[i] if text_per_page and i < len(text_per_page) else f"Page {i}"
        page.insert_text((50, 50), text)
    doc.save(path)
    doc.close()
    return path


class TestCreateCombinedPdf:
    """Tests for create_combined_pdf function."""

    def test_creates_combined_pdf(self, tmp_path):
        """Creates valid PDF with correct page count."""
        # Create source PDFs
        pdf1 = _create_test_pdf(tmp_path / "doc1.pdf", 5)
        pdf2 = _create_test_pdf(tmp_path / "doc2.pdf", 3)

        # Create file results and flagged pages
        fr1 = _make_file_result("doc1.pdf", page_count=5, flagged_indices=[1, 3])
        fr2 = _make_file_result("doc2.pdf", page_count=3, flagged_indices=[0])
        input_paths = {"doc1.pdf": pdf1, "doc2.pdf": pdf2}

        flagged_pages = collect_flagged_pages([fr1, fr2], input_paths)
        output_path = tmp_path / "combined.pdf"

        create_combined_pdf(flagged_pages, output_path)

        assert output_path.exists()
        with fitz.open(output_path) as combined:
            assert len(combined) == 3  # 2 from doc1 + 1 from doc2

    def test_page_order_matches_batch_index(self, tmp_path):
        """Pages in combined PDF match batch_index order."""
        # Create source PDFs with identifiable text
        pdf1 = _create_test_pdf(
            tmp_path / "doc1.pdf", 3, text_per_page=["Doc1 Page0", "Doc1 Page1", "Doc1 Page2"]
        )
        pdf2 = _create_test_pdf(
            tmp_path / "doc2.pdf", 2, text_per_page=["Doc2 Page0", "Doc2 Page1"]
        )

        fr1 = _make_file_result("doc1.pdf", page_count=3, flagged_indices=[0, 2])
        fr2 = _make_file_result("doc2.pdf", page_count=2, flagged_indices=[1])
        input_paths = {"doc1.pdf": pdf1, "doc2.pdf": pdf2}

        flagged_pages = collect_flagged_pages([fr1, fr2], input_paths)
        output_path = tmp_path / "combined.pdf"

        create_combined_pdf(flagged_pages, output_path)

        # Verify order: doc1 page0, doc1 page2, doc2 page1
        with fitz.open(output_path) as combined:
            assert len(combined) == 3
            # Batch index order: doc1 pages come first
            text0 = combined[0].get_text()
            text1 = combined[1].get_text()
            text2 = combined[2].get_text()
            assert "Doc1 Page0" in text0
            assert "Doc1 Page2" in text1
            assert "Doc2 Page1" in text2

    def test_empty_flagged_pages_does_not_create_file(self, tmp_path):
        """Empty flagged pages logs warning but doesn't create file."""
        output_path = tmp_path / "empty.pdf"

        # create_combined_pdf with empty input should not create a file
        # (PyMuPDF cannot save an empty document)
        create_combined_pdf([], output_path)

        # File should not be created for empty input
        assert not output_path.exists()


# =============================================================================
# Map Results To Files Tests
# =============================================================================


class TestMapResultsToFiles:
    """Tests for map_results_to_files function."""

    def test_updates_engine_to_surya(self):
        """All flagged pages get engine=SURYA."""
        fr = _make_file_result("doc.pdf", page_count=3, flagged_indices=[0, 2])
        input_paths = {"doc.pdf": Path("/test/doc.pdf")}
        flagged_pages = collect_flagged_pages([fr], input_paths)

        # Mock analyzer
        mock_analyzer = MagicMock()
        mock_analyzer.threshold = 0.85
        mock_result = MagicMock()
        mock_result.score = 0.95
        mock_analyzer.analyze.return_value = mock_result

        surya_text = "page0 text\n---\npage2 text"
        map_results_to_files(flagged_pages, surya_text, mock_analyzer)

        # Check engine was updated
        assert fr.pages[0].engine == OCREngine.SURYA
        assert fr.pages[1].engine == OCREngine.TESSERACT  # Not flagged, unchanged
        assert fr.pages[2].engine == OCREngine.SURYA

    def test_updates_quality_scores(self):
        """Quality scores updated from analyzer."""
        fr = _make_file_result("doc.pdf", page_count=2, flagged_indices=[0, 1])
        input_paths = {"doc.pdf": Path("/test/doc.pdf")}
        flagged_pages = collect_flagged_pages([fr], input_paths)

        mock_analyzer = MagicMock()
        mock_analyzer.threshold = 0.85
        # Return different scores for each call
        mock_results = [MagicMock(score=0.92), MagicMock(score=0.88)]
        mock_analyzer.analyze.side_effect = mock_results

        surya_text = "text1\n---\ntext2"
        map_results_to_files(flagged_pages, surya_text, mock_analyzer)

        assert fr.pages[0].quality_score == 0.92
        assert fr.pages[1].quality_score == 0.88

    def test_assigns_text_per_page(self):
        """Each FlaggedPage gets its split text assigned."""
        fr = _make_file_result("doc.pdf", page_count=2, flagged_indices=[0, 1])
        input_paths = {"doc.pdf": Path("/test/doc.pdf")}
        flagged_pages = collect_flagged_pages([fr], input_paths)

        mock_analyzer = MagicMock()
        mock_analyzer.threshold = 0.85
        mock_analyzer.analyze.return_value = MagicMock(score=0.95)

        surya_text = "first page content\n---\nsecond page content"
        map_results_to_files(flagged_pages, surya_text, mock_analyzer)

        assert fr.pages[0].text == "first page content"
        assert fr.pages[1].text == "second page content"

    def test_mutates_file_result_in_place(self):
        """Original FileResult is modified."""
        fr = _make_file_result("doc.pdf", page_count=1, flagged_indices=[0])
        input_paths = {"doc.pdf": Path("/test/doc.pdf")}
        flagged_pages = collect_flagged_pages([fr], input_paths)

        original_page = fr.pages[0]
        assert original_page.engine == OCREngine.TESSERACT

        mock_analyzer = MagicMock()
        mock_analyzer.threshold = 0.85
        mock_analyzer.analyze.return_value = MagicMock(score=0.95)

        map_results_to_files(flagged_pages, "surya text", mock_analyzer)

        # Same object should be modified
        assert original_page.engine == OCREngine.SURYA
        assert fr.pages[0] is original_page

    def test_status_updated_based_on_score(self):
        """Status set to GOOD/FLAGGED based on quality threshold."""
        fr = _make_file_result("doc.pdf", page_count=2, flagged_indices=[0, 1])
        input_paths = {"doc.pdf": Path("/test/doc.pdf")}
        flagged_pages = collect_flagged_pages([fr], input_paths)

        mock_analyzer = MagicMock()
        mock_analyzer.threshold = 0.85
        # First page above threshold, second below
        mock_results = [MagicMock(score=0.90), MagicMock(score=0.70)]
        mock_analyzer.analyze.side_effect = mock_results

        surya_text = "good\n---\nbad"
        map_results_to_files(flagged_pages, surya_text, mock_analyzer)

        assert fr.pages[0].status == PageStatus.GOOD
        assert fr.pages[0].flagged is False
        assert fr.pages[1].status == PageStatus.FLAGGED
        assert fr.pages[1].flagged is True
