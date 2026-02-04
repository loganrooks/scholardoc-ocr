"""Tests for device detection and validation module."""

import platform

import pytest

from scholardoc_ocr.device import DeviceInfo, DeviceType, detect_device

# Mark MPS tests to skip on non-macOS
IS_MACOS = platform.system() == "Darwin"
IS_APPLE_SILICON = IS_MACOS and platform.machine() == "arm64"


class TestDeviceType:
    """Tests for DeviceType enum."""

    def test_cuda_value(self):
        """CUDA enum value is 'cuda' string."""
        assert DeviceType.CUDA == "cuda"
        assert str(DeviceType.CUDA) == "cuda"

    def test_mps_value(self):
        """MPS enum value is 'mps' string."""
        assert DeviceType.MPS == "mps"
        assert str(DeviceType.MPS) == "mps"

    def test_cpu_value(self):
        """CPU enum value is 'cpu' string."""
        assert DeviceType.CPU == "cpu"
        assert str(DeviceType.CPU) == "cpu"

    def test_enum_members(self):
        """All expected enum members exist."""
        members = list(DeviceType)
        assert len(members) == 3
        assert DeviceType.CUDA in members
        assert DeviceType.MPS in members
        assert DeviceType.CPU in members


class TestDeviceInfo:
    """Tests for DeviceInfo dataclass."""

    def test_default_values(self):
        """DeviceInfo has correct default values."""
        info = DeviceInfo(
            device_type=DeviceType.CPU,
            device_name="cpu",
        )
        assert info.validated is False
        assert info.fallback_from is None

    def test_custom_values(self):
        """DeviceInfo accepts custom values including fallback_from."""
        info = DeviceInfo(
            device_type=DeviceType.CPU,
            device_name="cpu",
            validated=True,
            fallback_from=DeviceType.MPS,
        )
        assert info.device_type == DeviceType.CPU
        assert info.device_name == "cpu"
        assert info.validated is True
        assert info.fallback_from == DeviceType.MPS

    def test_device_type_required(self):
        """DeviceInfo requires device_type."""
        with pytest.raises(TypeError):
            DeviceInfo(device_name="cpu")  # type: ignore

    def test_device_name_required(self):
        """DeviceInfo requires device_name."""
        with pytest.raises(TypeError):
            DeviceInfo(device_type=DeviceType.CPU)  # type: ignore


class TestDetectDevice:
    """Tests for detect_device function."""

    @pytest.fixture
    def device_info(self):
        """Fixture providing detected device info."""
        return detect_device()

    def test_returns_device_info(self, device_info):
        """detect_device returns DeviceInfo instance."""
        assert isinstance(device_info, DeviceInfo)

    def test_returns_valid_device_type(self, device_info):
        """detect_device returns a valid DeviceType."""
        assert device_info.device_type in list(DeviceType)

    def test_device_is_validated(self, device_info):
        """detect_device marks device as validated."""
        assert device_info.validated is True

    def test_device_name_not_empty(self, device_info):
        """detect_device provides non-empty device name."""
        assert device_info.device_name
        assert len(device_info.device_name) > 0

    def test_idempotent(self):
        """detect_device is idempotent (multiple calls return same result)."""
        first = detect_device()
        second = detect_device()
        assert first.device_type == second.device_type
        assert first.device_name == second.device_name
        assert first.validated == second.validated

    def test_multiple_calls_consistent(self):
        """Multiple detect_device calls produce consistent results."""
        results = [detect_device() for _ in range(3)]
        device_types = [r.device_type for r in results]
        device_names = [r.device_name for r in results]

        assert len(set(device_types)) == 1, "Device type should be consistent"
        assert len(set(device_names)) == 1, "Device name should be consistent"


@pytest.mark.skipif(not IS_APPLE_SILICON, reason="MPS only available on Apple Silicon")
class TestMPSDetection:
    """Tests specific to MPS device detection on Apple Silicon."""

    def test_mps_detected_on_apple_silicon(self):
        """On Apple Silicon, MPS should be detected (unless CUDA is available)."""
        device_info = detect_device()
        # Either MPS or CUDA (if external GPU) should be available
        assert device_info.device_type in (DeviceType.MPS, DeviceType.CUDA)

    def test_mps_device_name(self):
        """MPS device should have 'Apple Silicon' as device name."""
        device_info = detect_device()
        if device_info.device_type == DeviceType.MPS:
            assert device_info.device_name == "Apple Silicon"


@pytest.mark.skipif(True, reason="CUDA tests require CUDA hardware")
class TestCUDADetection:
    """Tests specific to CUDA device detection.

    These tests are skipped by default as they require CUDA hardware.
    To run them, modify the skipif condition based on torch.cuda.is_available().
    """

    def test_cuda_detected_when_available(self):
        """CUDA should be detected when available."""
        import torch

        if torch.cuda.is_available():
            device_info = detect_device()
            assert device_info.device_type == DeviceType.CUDA

    def test_cuda_device_name_contains_gpu_info(self):
        """CUDA device name should contain GPU information."""
        import torch

        if torch.cuda.is_available():
            device_info = detect_device()
            if device_info.device_type == DeviceType.CUDA:
                # Device names are like "NVIDIA GeForce RTX 3090"
                assert device_info.device_name
                assert len(device_info.device_name) > 3


class TestFallbackBehavior:
    """Tests for device fallback behavior."""

    def test_cpu_always_available(self):
        """CPU device should always be available as fallback."""
        # Even if we can't test actual fallback, verify CPU is a valid result
        device_info = detect_device()
        # Result is always one of the valid device types
        assert device_info.device_type in (DeviceType.CUDA, DeviceType.MPS, DeviceType.CPU)

    def test_fallback_from_is_none_when_no_fallback(self):
        """fallback_from should be None when no fallback occurred."""
        device_info = detect_device()
        # If using preferred device (not CPU), fallback_from should be None
        # If using CPU due to no GPU, fallback_from may or may not be set
        # This just ensures the attribute exists and is the right type
        assert device_info.fallback_from is None or isinstance(
            device_info.fallback_from, DeviceType
        )


class TestGPUAvailabilityCheck:
    """Tests for check_gpu_availability function in environment.py."""

    def test_check_gpu_availability_returns_tuple(self):
        """check_gpu_availability returns tuple of (bool, str)."""
        from scholardoc_ocr.environment import check_gpu_availability

        available, message = check_gpu_availability()
        assert isinstance(available, bool)
        assert isinstance(message, str)
        assert len(message) > 0

    def test_check_gpu_availability_message_is_actionable(self):
        """Message should contain useful info about GPU status."""
        from scholardoc_ocr.environment import check_gpu_availability

        available, message = check_gpu_availability()
        # Message should contain one of these indicators
        expected_keywords = ["CUDA", "MPS", "GPU", "CPU", "available", "not"]
        assert any(kw.lower() in message.lower() for kw in expected_keywords)


class TestPipelineConfigStrictGPU:
    """Tests for strict_gpu field in PipelineConfig."""

    def test_pipeline_config_has_strict_gpu(self):
        """PipelineConfig should have strict_gpu field."""
        from scholardoc_ocr.pipeline import PipelineConfig

        config = PipelineConfig()
        assert hasattr(config, "strict_gpu")
        assert config.strict_gpu is False  # Default value

    def test_pipeline_config_strict_gpu_can_be_set(self):
        """strict_gpu can be set to True."""
        from scholardoc_ocr.pipeline import PipelineConfig

        config = PipelineConfig(strict_gpu=True)
        assert config.strict_gpu is True


class TestCLIStrictGPUFlag:
    """Tests for --strict-gpu CLI flag."""

    def test_cli_strict_gpu_flag_in_help(self):
        """--strict-gpu flag should appear in CLI help output."""
        import subprocess

        result = subprocess.run(
            ["ocr", "--help"],
            capture_output=True,
            text=True,
        )
        assert "--strict-gpu" in result.stdout

    def test_cli_strict_gpu_help_text(self):
        """--strict-gpu should have meaningful help text."""
        import subprocess

        result = subprocess.run(
            ["ocr", "--help"],
            capture_output=True,
            text=True,
        )
        # Check that help text mentions GPU and CPU fallback
        assert "GPU" in result.stdout or "gpu" in result.stdout
        assert "CPU" in result.stdout or "cpu" in result.stdout or "fall" in result.stdout


class TestConvertPdfWithFallback:
    """Tests for convert_pdf_with_fallback function."""

    def test_convert_pdf_with_fallback_exists(self):
        """convert_pdf_with_fallback function should exist and be callable."""
        from scholardoc_ocr.surya import convert_pdf_with_fallback

        assert callable(convert_pdf_with_fallback)

    def test_convert_pdf_with_fallback_falls_back_on_error(self, tmp_path, monkeypatch):
        """Verify fallback to CPU when GPU conversion fails."""
        from scholardoc_ocr import surya

        # Create a minimal mock PDF path
        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        # Track which device was used
        calls = []

        def mock_convert_pdf(input_path, model_dict, config=None, page_range=None):
            device = model_dict.get("_test_device", "unknown")
            calls.append(device)
            if device != "cpu":
                raise RuntimeError("Mock GPU failure")
            return "mock markdown"

        def mock_load_models(device=None):
            return {"_test_device": device or "gpu"}, device or "gpu"

        monkeypatch.setattr(surya, "convert_pdf", mock_convert_pdf)
        monkeypatch.setattr(surya, "load_models", mock_load_models)

        model_dict = {"_test_device": "gpu"}
        markdown, fallback = surya.convert_pdf_with_fallback(
            pdf_path, model_dict, strict_gpu=False
        )

        assert fallback is True
        assert markdown == "mock markdown"
        assert "cpu" in calls  # Should have retried on CPU

    def test_convert_pdf_with_fallback_strict_gpu_raises(self, tmp_path, monkeypatch):
        """Verify strict_gpu=True raises instead of falling back."""
        from scholardoc_ocr import surya
        from scholardoc_ocr.exceptions import SuryaError

        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        def mock_convert_pdf(*args, **kwargs):
            raise RuntimeError("Mock GPU failure")

        monkeypatch.setattr(surya, "convert_pdf", mock_convert_pdf)

        model_dict = {}
        with pytest.raises(SuryaError) as exc_info:
            surya.convert_pdf_with_fallback(pdf_path, model_dict, strict_gpu=True)

        assert "strict_gpu=True" in str(exc_info.value)

    def test_convert_pdf_with_fallback_success_no_fallback(self, tmp_path, monkeypatch):
        """Verify no fallback when GPU conversion succeeds."""
        from scholardoc_ocr import surya

        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        def mock_convert_pdf(input_path, model_dict, config=None, page_range=None):
            return "successful gpu markdown"

        monkeypatch.setattr(surya, "convert_pdf", mock_convert_pdf)

        model_dict = {}
        markdown, fallback = surya.convert_pdf_with_fallback(
            pdf_path, model_dict, strict_gpu=False
        )

        assert fallback is False
        assert markdown == "successful gpu markdown"

    def test_convert_pdf_with_fallback_returns_tuple(self, tmp_path, monkeypatch):
        """Verify function returns a tuple of (str, bool)."""
        from scholardoc_ocr import surya

        pdf_path = tmp_path / "test.pdf"
        pdf_path.touch()

        def mock_convert_pdf(input_path, model_dict, config=None, page_range=None):
            return "markdown"

        monkeypatch.setattr(surya, "convert_pdf", mock_convert_pdf)

        model_dict = {}
        result = surya.convert_pdf_with_fallback(pdf_path, model_dict)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], bool)
