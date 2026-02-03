"""Benchmark tests for Surya model loading time (BENCH-01, BENCH-02, BENCH-05)."""

import pytest

from scholardoc_ocr import surya
from scholardoc_ocr.timing import mps_sync

pytestmark = pytest.mark.skipif(
    not surya.is_available(),
    reason="Marker/Surya not installed",
)


def test_model_loading_cold_start(benchmark, hardware_profile):
    """Benchmark Surya model loading (cold start).

    Measures the time to load all Surya/Marker models from disk.
    This is the baseline for model caching optimization (Phase 13).

    The hardware_profile fixture (M1/M2/M3/M4/cpu) is used by pytest-benchmark
    to group results, enabling hardware-specific baseline comparisons (BENCH-05).
    """

    def load_models():
        models = surya.load_models()
        mps_sync()  # Ensure GPU work completes before timing stops
        return models

    # Use pedantic mode for expensive operations
    # warmup_rounds=0 for true cold-start measurement
    # rounds=3 for statistical validity without excessive time
    result = benchmark.pedantic(
        load_models,
        rounds=3,
        warmup_rounds=0,
        iterations=1,
    )
    assert result is not None
    assert "layout" in result or "detection" in result  # Has expected model keys
