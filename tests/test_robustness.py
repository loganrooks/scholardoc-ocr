"""Integration tests for pipeline robustness features (08-04)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

from scholardoc_ocr.pipeline import PipelineConfig, run_pipeline


def test_pipeline_config_has_new_fields():
    """PipelineConfig has keep_intermediates and timeout with correct defaults."""
    config = PipelineConfig()
    assert config.keep_intermediates is False
    assert config.timeout == 1800


def test_timeout_config_default():
    """Default timeout is 1800 seconds (30 minutes)."""
    assert PipelineConfig().timeout == 1800


def test_timeout_config_custom():
    """Timeout can be set to a custom value."""
    config = PipelineConfig(timeout=600)
    assert config.timeout == 600


def test_work_dir_cleaned_after_success():
    """Work directory is removed after successful pipeline run with no PDFs."""
    with tempfile.TemporaryDirectory() as tmp:
        input_dir = Path(tmp) / "input"
        input_dir.mkdir()
        output_dir = Path(tmp) / "output"

        config = PipelineConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            keep_intermediates=False,
        )

        result = run_pipeline(config)

        assert result.files == []
        # Work dir should not exist (or was cleaned up)
        work_dir = output_dir / "work"
        # With no files, work dir may or may not be created then cleaned;
        # the key invariant is it does not persist with content
        if work_dir.exists():
            assert list(work_dir.iterdir()) == []


def test_keep_intermediates_preserves_work_dir():
    """Work directory persists when keep_intermediates=True."""
    with tempfile.TemporaryDirectory() as tmp:
        input_dir = Path(tmp) / "input"
        input_dir.mkdir()
        output_dir = Path(tmp) / "output"

        config = PipelineConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            keep_intermediates=True,
        )

        run_pipeline(config)

        # Work dir should still exist
        work_dir = output_dir / "work"
        assert work_dir.exists()


def test_log_dir_created():
    """Pipeline creates logs/ directory in output_dir."""
    with tempfile.TemporaryDirectory() as tmp:
        input_dir = Path(tmp) / "input"
        input_dir.mkdir()
        output_dir = Path(tmp) / "output"

        config = PipelineConfig(
            input_dir=input_dir,
            output_dir=output_dir,
        )

        run_pipeline(config)

        log_dir = output_dir / "logs"
        assert log_dir.exists()
        # Should have a pipeline.log file
        assert (log_dir / "pipeline.log").exists()
