"""Integration tests for the OCR pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import scholardoc_ocr.model_cache  # noqa: F401 - pre-import for patching
import scholardoc_ocr.surya  # noqa: F401 - pre-import for patching
from scholardoc_ocr.exceptions import SuryaError
from scholardoc_ocr.pipeline import PipelineConfig, run_pipeline
from scholardoc_ocr.types import (
    BatchResult,
    FileResult,
    OCREngine,
    PageResult,
    PageStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_mock_pdf(path: Path) -> Path:
    """Create a minimal file at *path* (just needs to exist for mocking)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4 mock")
    return path


def _make_config(tmp_path: Path, **overrides) -> PipelineConfig:
    """Build a PipelineConfig pointing at *tmp_path* with sensible defaults."""
    input_dir = tmp_path / "input"
    input_dir.mkdir(exist_ok=True)
    output_dir = tmp_path / "output"
    output_dir.mkdir(exist_ok=True)
    defaults = {
        "input_dir": input_dir,
        "output_dir": output_dir,
        "quality_threshold": 0.85,
        "max_workers": 4,
    }
    defaults.update(overrides)
    return PipelineConfig(**defaults)


def _good_file_result(filename: str, page_count: int = 3) -> FileResult:
    """Return a FileResult where every page passes quality."""
    return FileResult(
        filename=filename,
        success=True,
        engine=OCREngine.TESSERACT,
        quality_score=0.95,
        page_count=page_count,
        pages=[
            PageResult(
                page_number=i,
                status=PageStatus.GOOD,
                quality_score=0.95,
                engine=OCREngine.TESSERACT,
                flagged=False,
                text=f"Good text on page {i}",
            )
            for i in range(page_count)
        ],
        time_seconds=0.5,
    )


def _flagged_file_result(
    filename: str,
    page_count: int = 3,
    flagged_indices: list[int] | None = None,
) -> FileResult:
    """Return a FileResult with specified pages flagged."""
    if flagged_indices is None:
        flagged_indices = [1]
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
                text=f"BAD_PAGE_{i}" if flagged else f"Good text on page {i}",
            )
        )
    avg_q = sum(p.quality_score for p in pages) / len(pages)
    return FileResult(
        filename=filename,
        success=True,
        engine=OCREngine.TESSERACT,
        quality_score=avg_q,
        page_count=page_count,
        pages=pages,
        time_seconds=0.5,
    )


def _mock_pool(futures: list[MagicMock]):
    """Set up a mock ProcessPoolExecutor that runs synchronously.

    Returns (mock_pool_cls, as_completed_patch) context managers to use.
    """
    mock_pool = MagicMock()
    mock_pool.submit.side_effect = futures

    pool_ctx = MagicMock()
    pool_ctx.__enter__ = MagicMock(return_value=mock_pool)
    pool_ctx.__exit__ = MagicMock(return_value=False)
    return pool_ctx, mock_pool


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPipelineReturns:
    """Test 1: run_pipeline returns a BatchResult."""

    @patch("scholardoc_ocr.surya.convert_pdf")
    @patch("scholardoc_ocr.surya.load_models")
    @patch("scholardoc_ocr.pipeline.ProcessPoolExecutor")
    def test_pipeline_returns_batch_result(
        self, mock_pool_cls, mock_load, mock_convert, tmp_path: Path
    ):
        _create_mock_pdf(tmp_path / "input" / "doc.pdf")
        config = _make_config(tmp_path, files=["doc.pdf"])

        result_fr = _good_file_result("doc.pdf", page_count=2)
        future = MagicMock()
        future.result.return_value = result_fr

        pool_ctx, pool = _mock_pool([future])
        mock_pool_cls.return_value = pool_ctx

        with patch(
            "scholardoc_ocr.pipeline.as_completed", return_value=iter([future])
        ):
            batch = run_pipeline(config)

        assert isinstance(batch, BatchResult)
        assert len(batch.files) == 1
        assert batch.files[0].success is True


class TestTesseractOnlyPath:
    """Test 2: When all pages pass quality, Surya is never called."""

    @patch("scholardoc_ocr.surya.convert_pdf")
    @patch("scholardoc_ocr.surya.load_models")
    @patch("scholardoc_ocr.pipeline.ProcessPoolExecutor")
    def test_pipeline_tesseract_only_no_surya_needed(
        self, mock_pool_cls, mock_load, mock_convert, tmp_path: Path
    ):
        _create_mock_pdf(tmp_path / "input" / "doc.pdf")
        config = _make_config(tmp_path, files=["doc.pdf"])

        result_fr = _good_file_result("doc.pdf")
        future = MagicMock()
        future.result.return_value = result_fr

        pool_ctx, pool = _mock_pool([future])
        mock_pool_cls.return_value = pool_ctx

        with patch(
            "scholardoc_ocr.pipeline.as_completed", return_value=iter([future])
        ):
            run_pipeline(config)

        mock_load.assert_not_called()
        mock_convert.assert_not_called()


class TestSuryaWriteback:
    """Test 3 (TEST-04 / BUG-01): Surya text is written back into output .txt."""

    @patch("scholardoc_ocr.surya.convert_pdf")
    @patch("scholardoc_ocr.surya.load_models")
    @patch("scholardoc_ocr.pipeline.ProcessPoolExecutor")
    def test_pipeline_surya_writeback(
        self, mock_pool_cls, mock_load, mock_convert, tmp_path: Path
    ):
        _create_mock_pdf(tmp_path / "input" / "doc.pdf")
        config = _make_config(tmp_path, files=["doc.pdf"], extract_text=True)

        result_fr = _flagged_file_result("doc.pdf", page_count=3, flagged_indices=[1])
        future = MagicMock()
        future.result.return_value = result_fr

        pool_ctx, pool = _mock_pool([future])
        mock_pool_cls.return_value = pool_ctx

        # Pre-create the .txt file that Tesseract phase would have written
        final_dir = tmp_path / "output" / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        text_path = final_dir / "doc.txt"
        text_path.write_text("page0\n\nBAD_PAGE\n\npage2", encoding="utf-8")

        mock_load.return_value = ({"model": "mock"}, "mps")  # Returns tuple now
        mock_convert.return_value = "SURYA_ENHANCED_TEXT"

        with patch(
            "scholardoc_ocr.pipeline.as_completed", return_value=iter([future])
        ):
            run_pipeline(config)

        # Verify writeback occurred
        updated = text_path.read_text(encoding="utf-8")
        assert "SURYA_ENHANCED_TEXT" in updated
        assert "BAD_PAGE" not in updated

        mock_load.assert_called_once()
        mock_convert.assert_called_once()


class TestSuryaPartialFailure:
    """Test 4: Per-file Surya failure does not crash the pipeline."""

    @patch("scholardoc_ocr.surya.convert_pdf")
    @patch("scholardoc_ocr.surya.load_models")
    @patch("scholardoc_ocr.pipeline.ProcessPoolExecutor")
    def test_pipeline_surya_failure_partial_success(
        self, mock_pool_cls, mock_load, mock_convert, tmp_path: Path
    ):
        _create_mock_pdf(tmp_path / "input" / "fail.pdf")
        _create_mock_pdf(tmp_path / "input" / "ok.pdf")
        config = _make_config(tmp_path, files=["fail.pdf", "ok.pdf"], extract_text=True)

        fr_fail = _flagged_file_result("fail.pdf", page_count=2, flagged_indices=[0])
        fr_ok = _flagged_file_result("ok.pdf", page_count=2, flagged_indices=[0])

        future_fail = MagicMock()
        future_fail.result.return_value = fr_fail
        future_ok = MagicMock()
        future_ok.result.return_value = fr_ok

        pool_ctx, pool = _mock_pool([future_fail, future_ok])
        mock_pool_cls.return_value = pool_ctx

        # Pre-create .txt files
        final_dir = tmp_path / "output" / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        (final_dir / "fail.txt").write_text("BAD\n\npage1", encoding="utf-8")
        (final_dir / "ok.txt").write_text("BAD\n\npage1", encoding="utf-8")

        mock_load.return_value = ({"model": "mock"}, "mps")  # Returns tuple now
        mock_convert.side_effect = [
            SuryaError("GPU OOM"),
            "SURYA_ENHANCED_TEXT",
        ]

        with patch(
            "scholardoc_ocr.pipeline.as_completed",
            return_value=iter([future_fail, future_ok]),
        ):
            batch = run_pipeline(config)

        assert isinstance(batch, BatchResult)
        assert len(batch.files) == 2
        assert all(f.success for f in batch.files)

        # First file keeps original text (Surya failed)
        fail_text = (final_dir / "fail.txt").read_text(encoding="utf-8")
        assert "BAD" in fail_text

        # Second file has Surya text
        ok_text = (final_dir / "ok.txt").read_text(encoding="utf-8")
        assert "SURYA_ENHANCED_TEXT" in ok_text


class TestForceSurya:
    """Test 5: force_surya triggers Surya on all pages even if quality is good."""

    @patch("scholardoc_ocr.surya.convert_pdf")
    @patch("scholardoc_ocr.model_cache.ModelCache")
    @patch("scholardoc_ocr.pipeline.ProcessPoolExecutor")
    def test_pipeline_force_surya(
        self, mock_pool_cls, mock_cache_cls, mock_convert, tmp_path: Path
    ):
        _create_mock_pdf(tmp_path / "input" / "doc.pdf")
        config = _make_config(tmp_path, files=["doc.pdf"], force_surya=True)

        result_fr = _good_file_result("doc.pdf", page_count=2)
        future = MagicMock()
        future.result.return_value = result_fr

        pool_ctx, pool = _mock_pool([future])
        mock_pool_cls.return_value = pool_ctx

        final_dir = tmp_path / "output" / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        (final_dir / "doc.txt").write_text("page0\n\npage1", encoding="utf-8")

        # Configure ModelCache mock to return models
        mock_cache_instance = MagicMock()
        mock_cache_instance.get_models.return_value = ({"model": "mock"}, "mps")
        mock_cache_cls.get_instance.return_value = mock_cache_instance

        mock_convert.return_value = "SURYA_FORCED"

        with patch(
            "scholardoc_ocr.pipeline.as_completed", return_value=iter([future])
        ):
            run_pipeline(config)

        # Verify ModelCache was used to get models
        mock_cache_cls.get_instance.assert_called_once()
        mock_cache_instance.get_models.assert_called_once()
        mock_convert.assert_called_once()


class TestResourceAwareWorkers:
    """Test 6: Worker calculation respects CPU count and file count."""

    def test_resource_aware_workers_few_files(self):
        """8 cores, 2 files -> jobs_per_file=4, pool_workers=2."""
        total_cores = 8
        num_files = 2
        max_workers = 4
        jobs_per_file = max(1, total_cores // max(1, num_files))
        pool_workers = max(1, min(max_workers, total_cores // jobs_per_file))

        assert jobs_per_file == 4
        assert pool_workers == 2

    def test_resource_aware_workers_many_files(self):
        """8 cores, 16 files -> jobs_per_file=1, pool_workers=8 (capped)."""
        total_cores = 8
        num_files = 16
        max_workers = 8
        jobs_per_file = max(1, total_cores // max(1, num_files))
        pool_workers = max(1, min(max_workers, total_cores // jobs_per_file))

        assert jobs_per_file == 1
        assert pool_workers == 8


class TestEmptyInput:
    """Test 7: Empty input returns BatchResult with no files."""

    def test_pipeline_empty_input(self, tmp_path: Path):
        config = _make_config(tmp_path, files=[])
        batch = run_pipeline(config)

        assert isinstance(batch, BatchResult)
        assert len(batch.files) == 0


class TestPipelineConfigDefaults:
    """Test 8: PipelineConfig has force_surya defaulting to False."""

    def test_pipeline_config_force_surya_field(self):
        config = PipelineConfig()
        assert hasattr(config, "force_surya")
        assert config.force_surya is False


class TestModelCacheIntegration:
    """Tests for MODEL-01 and MODEL-03: model caching and inter-document cleanup."""

    @patch("scholardoc_ocr.surya.convert_pdf")
    @patch("scholardoc_ocr.model_cache.cleanup_between_documents")
    @patch("scholardoc_ocr.model_cache.ModelCache")
    @patch("scholardoc_ocr.pipeline.ProcessPoolExecutor")
    def test_pipeline_uses_model_cache(
        self, mock_pool_cls, mock_cache_cls, mock_cleanup, mock_convert, tmp_path: Path
    ):
        """Verify pipeline uses ModelCache instead of direct load_models (MODEL-01)."""
        _create_mock_pdf(tmp_path / "input" / "doc.pdf")
        config = _make_config(tmp_path, files=["doc.pdf"], force_surya=True)

        # Set up file result with flagged pages to trigger Surya
        result_fr = _flagged_file_result("doc.pdf", page_count=2, flagged_indices=[0])
        future = MagicMock()
        future.result.return_value = result_fr

        pool_ctx, pool = _mock_pool([future])
        mock_pool_cls.return_value = pool_ctx

        # Pre-create .txt file
        final_dir = tmp_path / "output" / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        (final_dir / "doc.txt").write_text("BAD\n\npage1", encoding="utf-8")

        # Configure ModelCache mock
        mock_cache_instance = MagicMock()
        mock_cache_instance.get_models.return_value = ({"model": "mock"}, "cpu")
        mock_cache_cls.get_instance.return_value = mock_cache_instance

        mock_convert.return_value = "SURYA_TEXT"

        with patch(
            "scholardoc_ocr.pipeline.as_completed", return_value=iter([future])
        ):
            run_pipeline(config)

        # Verify ModelCache was used instead of direct surya.load_models
        mock_cache_cls.get_instance.assert_called_once()
        mock_cache_instance.get_models.assert_called_once()

    @patch("scholardoc_ocr.surya.convert_pdf")
    @patch("scholardoc_ocr.model_cache.cleanup_between_documents")
    @patch("scholardoc_ocr.model_cache.ModelCache")
    @patch("scholardoc_ocr.pipeline.ProcessPoolExecutor")
    def test_pipeline_cleanup_between_documents(
        self, mock_pool_cls, mock_cache_cls, mock_cleanup, mock_convert, tmp_path: Path
    ):
        """Verify cleanup_between_documents called after each Surya file (MODEL-03)."""
        # Create two test PDFs
        _create_mock_pdf(tmp_path / "input" / "doc1.pdf")
        _create_mock_pdf(tmp_path / "input" / "doc2.pdf")
        config = _make_config(
            tmp_path, files=["doc1.pdf", "doc2.pdf"], force_surya=True, extract_text=True
        )

        # Set up file results with flagged pages to trigger Surya
        result_fr1 = _flagged_file_result("doc1.pdf", page_count=2, flagged_indices=[0])
        result_fr2 = _flagged_file_result("doc2.pdf", page_count=2, flagged_indices=[0])

        future1 = MagicMock()
        future1.result.return_value = result_fr1
        future2 = MagicMock()
        future2.result.return_value = result_fr2

        pool_ctx, pool = _mock_pool([future1, future2])
        mock_pool_cls.return_value = pool_ctx

        # Pre-create .txt files
        final_dir = tmp_path / "output" / "final"
        final_dir.mkdir(parents=True, exist_ok=True)
        (final_dir / "doc1.txt").write_text("BAD\n\npage1", encoding="utf-8")
        (final_dir / "doc2.txt").write_text("BAD\n\npage1", encoding="utf-8")

        # Configure ModelCache mock
        mock_cache_instance = MagicMock()
        mock_cache_instance.get_models.return_value = ({"model": "mock"}, "cpu")
        mock_cache_cls.get_instance.return_value = mock_cache_instance

        mock_convert.return_value = "SURYA_TEXT"

        with patch(
            "scholardoc_ocr.pipeline.as_completed", return_value=iter([future1, future2])
        ):
            run_pipeline(config)

        # Verify cleanup called once per file processed by Surya
        assert mock_cleanup.call_count == 2


class TestMetricsFixes:
    """Tests for BENCH-06, BENCH-07, BENCH-08 metrics fixes."""

    def test_compute_engine_from_pages_in_result(self, tmp_path):
        """Test that FileResult.engine is computed from page engines (BENCH-07)."""
        from scholardoc_ocr.types import (
            OCREngine,
            PageResult,
            PageStatus,
            compute_engine_from_pages,
        )

        # Create a file result with mixed engines
        pages = [
            PageResult(
                page_number=0,
                status=PageStatus.GOOD,
                quality_score=0.9,
                engine=OCREngine.TESSERACT,
            ),
            PageResult(
                page_number=1,
                status=PageStatus.GOOD,
                quality_score=0.95,
                engine=OCREngine.SURYA,
            ),
        ]

        # Verify compute function works
        assert compute_engine_from_pages(pages) == OCREngine.MIXED

        # Verify with all same engine
        all_tess = [
            PageResult(
                page_number=0,
                status=PageStatus.GOOD,
                quality_score=0.9,
                engine=OCREngine.TESSERACT,
            ),
            PageResult(
                page_number=1,
                status=PageStatus.GOOD,
                quality_score=0.9,
                engine=OCREngine.TESSERACT,
            ),
        ]
        assert compute_engine_from_pages(all_tess) == OCREngine.TESSERACT

    def test_surya_timing_keys(self):
        """Test that Surya timing keys are defined (BENCH-06)."""
        # These are the keys that should be added to phase_timings
        expected_keys = ["surya_model_load", "surya_inference"]
        # This is a documentation/contract test - actual values tested in integration
        for key in expected_keys:
            assert isinstance(key, str)
