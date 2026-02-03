"""Tests for environment validation and startup diagnostics."""

from __future__ import annotations

import logging
import shutil
import subprocess
from unittest.mock import patch

import pytest

from scholardoc_ocr.environment import (
    EnvironmentError,
    log_startup_diagnostics,
    validate_environment,
)


@pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract not installed"
)
def test_validate_environment_passes_when_tesseract_available():
    """On a system with tesseract, validation should not raise."""
    # May raise if specific langs missing; use only eng which is always present
    validate_environment(langs_tesseract="eng")


def test_validate_environment_raises_when_tesseract_missing():
    """When tesseract binary is not found, raise with clear message."""
    with patch("scholardoc_ocr.environment.shutil.which", return_value=None):
        with pytest.raises(EnvironmentError, match="tesseract not found"):
            validate_environment()


def test_validate_environment_raises_for_missing_lang():
    """When a required language pack is missing, raise with that lang name."""
    mock_result = subprocess.CompletedProcess(
        args=["tesseract", "--list-langs"],
        returncode=0,
        stdout="List of available languages (1):\neng\n",
        stderr="",
    )
    with (
        patch(
            "scholardoc_ocr.environment.shutil.which",
            return_value="/usr/bin/tesseract",
        ),
        patch(
            "scholardoc_ocr.environment.subprocess.run",
            return_value=mock_result,
        ),
    ):
        with pytest.raises(EnvironmentError, match="fra"):
            validate_environment(langs_tesseract="eng,fra")


def test_log_startup_diagnostics_no_crash(caplog):
    """Diagnostics logging should not raise regardless of environment."""
    with caplog.at_level(logging.INFO):
        log_startup_diagnostics()
    assert len(caplog.records) > 0


def test_environment_error_has_problems_list():
    """EnvironmentError should expose a problems list attribute."""
    err = EnvironmentError(["problem 1", "problem 2"])
    assert isinstance(err.problems, list)
    assert len(err.problems) == 2
    assert "problem 1" in err.problems
