"""Unit tests for Surya/Marker OCR backend module.

All tests mock marker/torch — no real ML models are loaded.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scholardoc_ocr.exceptions import SuryaError
from scholardoc_ocr.surya import SuryaConfig, is_available


class TestSuryaConfig:
    def test_defaults(self):
        cfg = SuryaConfig()
        assert cfg.langs == "en,fr,el,la"
        assert cfg.force_ocr is True
        assert cfg.batch_size == 50
        assert cfg.model_load_timeout == 300.0
        assert cfg.batch_timeout == 1200.0

    def test_custom_values(self):
        cfg = SuryaConfig(langs="en", force_ocr=False, batch_size=10)
        assert cfg.langs == "en"
        assert cfg.force_ocr is False
        assert cfg.batch_size == 10


class TestIsAvailable:
    def test_available_when_marker_installed(self):
        with patch("importlib.import_module") as mock_import:
            mock_import.return_value = MagicMock()
            assert is_available() is True
            mock_import.assert_called_once_with("marker")

    def test_unavailable_when_marker_missing(self):
        with patch("importlib.import_module", side_effect=ImportError):
            assert is_available() is False


class TestLoadModels:
    @patch("scholardoc_ocr.surya.logger")
    def test_success(self, _mock_logger):
        fake_models = {"model_a": "fake", "model_b": "fake"}
        mock_create = MagicMock(return_value=fake_models)

        with patch.dict("sys.modules", {"marker": MagicMock(), "marker.models": MagicMock()}):
            with patch("marker.models.create_model_dict", mock_create, create=True):
                # Re-import to pick up patched module
                import importlib

                import scholardoc_ocr.surya as surya_mod

                importlib.reload(surya_mod)

                result = surya_mod.load_models()

        assert result == fake_models

    @patch("scholardoc_ocr.surya.logger")
    def test_with_device(self, _mock_logger):
        fake_models = {"model": "fake"}
        mock_create = MagicMock(return_value=fake_models)
        mock_torch = MagicMock()
        mock_torch.device.return_value = "cuda:0"

        with patch.dict(
            "sys.modules",
            {
                "marker": MagicMock(),
                "marker.models": MagicMock(),
                "torch": mock_torch,
            },
        ):
            with patch("marker.models.create_model_dict", mock_create, create=True):
                import importlib

                import scholardoc_ocr.surya as surya_mod

                importlib.reload(surya_mod)

                result = surya_mod.load_models(device="cuda:0")

        assert result == fake_models
        mock_torch.device.assert_called_once_with("cuda:0")

    def test_failure_raises_surya_error(self):
        mock_create = MagicMock(side_effect=RuntimeError("GPU OOM"))

        with patch.dict("sys.modules", {"marker": MagicMock(), "marker.models": MagicMock()}):
            with patch("marker.models.create_model_dict", mock_create, create=True):
                import importlib

                import scholardoc_ocr.surya as surya_mod

                importlib.reload(surya_mod)

                with pytest.raises(SuryaError, match="Failed to load"):
                    surya_mod.load_models()

    def test_missing_marker_raises_surya_error(self):
        """load_models raises SuryaError when marker is not installed."""
        with patch.dict("sys.modules", {"marker": None, "marker.models": None}):
            import importlib

            import scholardoc_ocr.surya as surya_mod

            importlib.reload(surya_mod)

            with pytest.raises(SuryaError, match="Marker package not installed"):
                surya_mod.load_models()


class TestConvertPdf:
    def test_success(self, tmp_path: Path):
        fake_pdf = tmp_path / "test.pdf"
        fake_pdf.write_bytes(b"%PDF-fake")

        mock_output = MagicMock()
        mock_output.markdown = "# Converted text\n\nHello world."

        mock_converter_cls = MagicMock()
        mock_converter_instance = MagicMock(return_value=mock_output)
        mock_converter_cls.return_value = mock_converter_instance

        mock_md_output = MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "marker": MagicMock(),
                "marker.converters": MagicMock(),
                "marker.converters.pdf": MagicMock(PdfConverter=mock_converter_cls),
                "marker.renderers": MagicMock(),
                "marker.renderers.markdown": MagicMock(MarkdownOutput=mock_md_output),
            },
        ):
            import importlib

            import scholardoc_ocr.surya as surya_mod

            importlib.reload(surya_mod)

            model_dict = {"model": "fake"}
            result = surya_mod.convert_pdf(fake_pdf, model_dict)

        assert result == "# Converted text\n\nHello world."
        mock_converter_cls.assert_called_once()
        call_kwargs = mock_converter_cls.call_args
        assert call_kwargs[1]["artifact_dict"] == model_dict

    def test_with_page_range(self, tmp_path: Path):
        fake_pdf = tmp_path / "test.pdf"
        fake_pdf.write_bytes(b"%PDF-fake")

        mock_output = MagicMock()
        mock_output.markdown = "page text"

        mock_converter_cls = MagicMock()
        mock_converter_cls.return_value = MagicMock(return_value=mock_output)

        with patch.dict(
            "sys.modules",
            {
                "marker": MagicMock(),
                "marker.converters": MagicMock(),
                "marker.converters.pdf": MagicMock(PdfConverter=mock_converter_cls),
                "marker.renderers": MagicMock(),
                "marker.renderers.markdown": MagicMock(),
            },
        ):
            import importlib

            import scholardoc_ocr.surya as surya_mod

            importlib.reload(surya_mod)

            result = surya_mod.convert_pdf(
                fake_pdf, {"m": "fake"}, page_range=[0, 2, 5]
            )

        assert result == "page text"
        call_kwargs = mock_converter_cls.call_args[1]
        assert call_kwargs["config"]["page_range"] == [0, 2, 5]

    def test_failure_raises_surya_error(self, tmp_path: Path):
        fake_pdf = tmp_path / "test.pdf"
        fake_pdf.write_bytes(b"%PDF-fake")

        mock_converter_cls = MagicMock()
        mock_converter_cls.return_value = MagicMock(
            side_effect=RuntimeError("conversion failed")
        )

        with patch.dict(
            "sys.modules",
            {
                "marker": MagicMock(),
                "marker.converters": MagicMock(),
                "marker.converters.pdf": MagicMock(PdfConverter=mock_converter_cls),
                "marker.renderers": MagicMock(),
                "marker.renderers.markdown": MagicMock(),
            },
        ):
            import importlib

            import scholardoc_ocr.surya as surya_mod

            importlib.reload(surya_mod)

            with pytest.raises(SuryaError, match="conversion failed"):
                surya_mod.convert_pdf(fake_pdf, {"m": "fake"})


class TestLazyImports:
    def test_no_torch_or_marker_on_import(self):
        """Importing surya module does not load torch or marker."""
        # Remove if previously loaded by other tests
        mods_to_check = ["torch", "marker"]
        saved = {}
        for mod in mods_to_check:
            if mod in sys.modules:
                saved[mod] = sys.modules.pop(mod)

        try:
            import importlib

            import scholardoc_ocr.surya as surya_mod

            importlib.reload(surya_mod)

            # Just accessing the module and SuryaConfig should not load ML deps
            _ = surya_mod.SuryaConfig()
            _ = surya_mod.is_available  # reference, don't call (would import marker)

            assert "torch" not in sys.modules
        finally:
            # Restore
            sys.modules.update(saved)


# Future integration tests (require real Surya models):
# @pytest.mark.integration
# def test_load_real_models():
#     """Load actual Surya models and verify dict structure."""
#
# @pytest.mark.integration
# def test_convert_real_pdf(sample_pdf):
#     """Convert a real PDF and verify markdown output."""
