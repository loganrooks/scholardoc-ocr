"""Unit tests for Tesseract OCR backend module."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from scholardoc_ocr.tesseract import TesseractConfig, is_available, run_ocr

MOCK_MODULES = {"ocrmypdf": None, "ocrmypdf.exceptions": None}


def _make_mock_ocrmypdf():
    """Create a mock ocrmypdf with exception types."""
    mock = MagicMock()
    mock.ExitCode.ok = 0
    mock.exceptions.PriorOcrFoundError = type(
        "PriorOcrFoundError", (Exception,), {}
    )
    mock.exceptions.MissingDependencyError = type(
        "MissingDependencyError", (Exception,), {}
    )
    modules = {
        "ocrmypdf": mock,
        "ocrmypdf.exceptions": mock.exceptions,
    }
    return mock, modules


class TestTesseractConfig:
    """Tests for TesseractConfig defaults."""

    def test_config_defaults(self):
        config = TesseractConfig()
        assert config.langs == ["eng", "fra", "ell", "lat"]
        assert config.jobs == 4
        assert config.timeout == 600.0
        assert config.skip_big == 100

    def test_config_custom(self):
        config = TesseractConfig(
            langs=["eng"], jobs=2, timeout=300.0, skip_big=50
        )
        assert config.langs == ["eng"]
        assert config.jobs == 2


class TestRunOcr:
    """Tests for run_ocr with mocked ocrmypdf."""

    def test_run_ocr_success(self, tmp_path: Path):
        input_pdf = tmp_path / "input.pdf"
        output_pdf = tmp_path / "output.pdf"
        input_pdf.touch()

        mock, modules = _make_mock_ocrmypdf()
        mock.ocr.return_value = 0

        with patch.dict("sys.modules", modules):
            result = run_ocr(input_pdf, output_pdf)

        assert result.success is True
        assert result.output_path == output_pdf

    def test_run_ocr_prior_ocr(self, tmp_path: Path):
        input_pdf = tmp_path / "input.pdf"
        output_pdf = tmp_path / "output.pdf"
        input_pdf.touch()

        mock, modules = _make_mock_ocrmypdf()
        prior_err = mock.exceptions.PriorOcrFoundError
        mock.ocr.side_effect = prior_err("already has OCR")

        with patch.dict("sys.modules", modules):
            result = run_ocr(input_pdf, output_pdf)

        assert result.success is True
        assert result.output_path == output_pdf

    def test_run_ocr_failure(self, tmp_path: Path):
        input_pdf = tmp_path / "input.pdf"
        output_pdf = tmp_path / "output.pdf"
        input_pdf.touch()

        mock, modules = _make_mock_ocrmypdf()
        mock.ocr.side_effect = RuntimeError("tesseract crashed")

        with patch.dict("sys.modules", modules):
            result = run_ocr(input_pdf, output_pdf)

        assert result.success is False
        assert "tesseract crashed" in result.error

    def test_run_ocr_missing_dependency(self, tmp_path: Path):
        input_pdf = tmp_path / "input.pdf"
        output_pdf = tmp_path / "output.pdf"
        input_pdf.touch()

        mock, modules = _make_mock_ocrmypdf()
        missing_err = mock.exceptions.MissingDependencyError
        mock.ocr.side_effect = missing_err("tesseract not found")

        with patch.dict("sys.modules", modules):
            result = run_ocr(input_pdf, output_pdf)

        assert result.success is False
        assert "Missing dependency" in result.error


class TestIsAvailable:
    """Tests for is_available."""

    def test_is_available_returns_bool(self):
        result = is_available()
        assert isinstance(result, bool)


class TestLazyImport:
    """Tests verifying lazy import behavior."""

    def test_lazy_import_no_ocrmypdf_at_module_level(self):
        """Verify ocrmypdf is not imported by importing tesseract."""
        # Remove from sys.modules if present
        to_remove = [k for k in sys.modules if k.startswith("ocrmypdf")]
        saved = {k: sys.modules.pop(k) for k in to_remove}

        try:
            if "scholardoc_ocr.tesseract" in sys.modules:
                del sys.modules["scholardoc_ocr.tesseract"]

            import importlib

            importlib.import_module("scholardoc_ocr.tesseract")

            assert "ocrmypdf" not in sys.modules
        finally:
            sys.modules.update(saved)


# Future integration tests would use @pytest.mark.integration
# and require real Tesseract installation.
# @pytest.mark.integration
# def test_run_ocr_real_pdf(tmp_path):
#     """Integration test with actual PDF - requires Tesseract."""
#     pass
