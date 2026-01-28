"""Exception hierarchy for the scholardoc-ocr pipeline."""

from __future__ import annotations


class ScholarDocError(Exception):
    """Base exception for all scholardoc-ocr errors."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def __str__(self) -> str:
        return self.message


class OCRError(ScholarDocError):
    """Error during OCR engine processing."""

    def __init__(
        self,
        message: str,
        filename: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.filename = filename


class TesseractError(OCRError):
    """Error specific to Tesseract OCR processing."""


class SuryaError(OCRError):
    """Error specific to Surya/Marker OCR processing."""


class PDFError(ScholarDocError):
    """Error during PDF read/write operations."""

    def __init__(
        self,
        message: str,
        pdf_path: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.pdf_path = pdf_path


class ConfigError(ScholarDocError):
    """Error due to invalid configuration."""

    def __init__(
        self,
        message: str,
        parameter: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.parameter = parameter


class DependencyError(ScholarDocError):
    """Error due to a missing external dependency."""

    def __init__(
        self,
        message: str,
        package: str | None = None,
        install_hint: str | None = None,
        details: dict | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.package = package
        self.install_hint = install_hint
