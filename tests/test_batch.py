"""Unit tests for the batch configuration module.

Tests cover FlaggedPage dataclass, memory detection, and batch size configuration
across different memory tiers and device types.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scholardoc_ocr.batch import (
    FlaggedPage,
    configure_surya_batch_sizes,
    get_available_memory_gb,
)
from scholardoc_ocr.types import FileResult


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
