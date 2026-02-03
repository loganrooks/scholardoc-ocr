"""Memory limit tests for OCR processing (BENCH-04)."""

import pytest

from scholardoc_ocr import surya
from scholardoc_ocr.surya import SuryaConfig

pytestmark = pytest.mark.skipif(
    not surya.is_available(),
    reason="Marker/Surya not installed",
)


@pytest.mark.limit_memory("2 GB")
def test_model_loading_memory(loaded_models):
    """Model loading should not exceed 2GB peak memory.

    This validates memory usage is reasonable for Apple Silicon devices.
    The loaded_models fixture triggers the load; this test just checks
    the memory limit marker.
    """
    assert loaded_models is not None


@pytest.mark.limit_memory("4 GB")
def test_single_page_inference_memory(loaded_models, sample_pdf):
    """Single page OCR should not exceed 4GB peak memory."""
    result = surya.convert_pdf(
        sample_pdf,
        loaded_models,
        config=SuryaConfig(langs="en"),
        page_range=[0],
    )
    assert len(result) > 0
