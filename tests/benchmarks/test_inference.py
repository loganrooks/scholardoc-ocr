"""Benchmark tests for Surya OCR inference (BENCH-01, BENCH-02, BENCH-05)."""

import pytest

from scholardoc_ocr import surya
from scholardoc_ocr.surya import SuryaConfig
from scholardoc_ocr.timing import mps_sync

pytestmark = pytest.mark.skipif(
    not surya.is_available(),
    reason="Marker/Surya not installed",
)


def test_single_page_inference(benchmark, loaded_models, sample_pdf, hardware_profile):
    """Benchmark single-page Surya inference.

    Uses pre-loaded models (session fixture) to measure pure inference time.
    The hardware_profile fixture enables BENCH-05 hardware-specific baselines.
    """

    def run_inference():
        result = surya.convert_pdf(
            sample_pdf,
            loaded_models,
            config=SuryaConfig(langs="en"),
            page_range=[0],  # Single page
        )
        mps_sync()
        return result

    result = benchmark.pedantic(
        run_inference,
        rounds=5,
        warmup_rounds=1,
        iterations=1,
    )
    assert isinstance(result, str)
    assert len(result) > 0
