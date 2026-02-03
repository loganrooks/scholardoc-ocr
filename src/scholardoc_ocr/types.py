"""Result types and enums for the scholardoc-ocr pipeline."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum

# ISO 639-1 to engine-specific language code mapping
LANGUAGE_MAP: dict[str, dict[str, str]] = {
    "en": {"tesseract": "eng", "surya": "en"},
    "fr": {"tesseract": "fra", "surya": "fr"},
    "de": {"tesseract": "deu", "surya": "de"},
    "el": {"tesseract": "ell", "surya": "el"},
    "la": {"tesseract": "lat", "surya": "la"},
}

_DEFAULT_TESSERACT = "eng,fra,ell,lat,deu"
_DEFAULT_SURYA = "en,fr,el,la,de"


def resolve_languages(iso_codes: list[str]) -> tuple[str, str]:
    """Resolve ISO 639-1 codes to Tesseract and Surya language strings.

    Args:
        iso_codes: List of ISO 639-1 language codes (e.g. ["en", "fr"]).
            If empty, returns default language sets.

    Returns:
        Tuple of (tesseract_langs, surya_langs) as comma-separated strings.

    Raises:
        ValueError: If an unrecognized language code is provided.
    """
    if not iso_codes:
        return (_DEFAULT_TESSERACT, _DEFAULT_SURYA)

    tess_langs = []
    surya_langs = []
    for code in iso_codes:
        if code not in LANGUAGE_MAP:
            raise ValueError(
                f"Unsupported language code: {code!r}. "
                f"Supported: {', '.join(sorted(LANGUAGE_MAP))}"
            )
        tess_langs.append(LANGUAGE_MAP[code]["tesseract"])
        surya_langs.append(LANGUAGE_MAP[code]["surya"])

    return (",".join(tess_langs), ",".join(surya_langs))


class OCREngine(StrEnum):
    """OCR engine used for processing."""

    TESSERACT = "tesseract"
    SURYA = "surya"
    EXISTING = "existing"
    MIXED = "mixed"  # When some pages used Tesseract, others used Surya
    NONE = "none"


class ProcessingPhase(StrEnum):
    """Pipeline processing phase."""

    ANALYSIS = "analysis"
    TESSERACT = "tesseract"
    SURYA = "surya"


class PageStatus(StrEnum):
    """Quality status of a processed page."""

    GOOD = "good"
    FLAGGED = "flagged"
    ERROR = "error"


@dataclass
class PageResult:
    """Result for a single page."""

    page_number: int
    status: PageStatus
    quality_score: float
    engine: OCREngine
    flagged: bool = False
    text: str | None = None

    def to_dict(self, include_text: bool = False) -> dict:
        """Convert to a JSON-serializable dictionary."""
        d: dict = {
            "page_number": self.page_number,
            "status": str(self.status),
            "quality_score": self.quality_score,
            "engine": str(self.engine),
            "flagged": self.flagged,
        }
        if include_text and self.text is not None:
            d["text"] = self.text
        return d


def compute_engine_from_pages(pages: list[PageResult]) -> OCREngine:
    """Determine top-level engine from per-page engines.

    Args:
        pages: List of PageResult objects with per-page engine values.

    Returns:
        - TESSERACT if all pages used Tesseract
        - SURYA if all pages used Surya
        - EXISTING if all pages had existing text
        - MIXED if multiple engines were used
        - NONE if no pages or all pages have NONE engine
    """
    engines = {p.engine for p in pages if p.engine != OCREngine.NONE}

    if not engines:
        return OCREngine.NONE
    if engines == {OCREngine.TESSERACT}:
        return OCREngine.TESSERACT
    if engines == {OCREngine.SURYA}:
        return OCREngine.SURYA
    if engines == {OCREngine.EXISTING}:
        return OCREngine.EXISTING
    # Multiple engines used = mixed
    return OCREngine.MIXED


@dataclass
class FileResult:
    """Result for a single file containing per-page details."""

    filename: str
    success: bool
    engine: OCREngine
    quality_score: float
    page_count: int
    pages: list[PageResult]
    error: str | None = None
    time_seconds: float = 0.0
    phase_timings: dict[str, float] = field(default_factory=dict)
    output_path: str | None = None

    @property
    def flagged_pages(self) -> list[PageResult]:
        """Pages that were flagged for quality issues."""
        return [p for p in self.pages if p.flagged]

    @property
    def page_scores(self) -> list[float]:
        """Quality scores for all pages."""
        return [p.quality_score for p in self.pages]

    def to_dict(self, include_text: bool = False) -> dict:
        """Convert to a JSON-serializable dictionary."""
        d: dict = {
            "filename": self.filename,
            "success": self.success,
            "engine": str(self.engine),
            "quality_score": self.quality_score,
            "page_count": self.page_count,
            "pages": [p.to_dict(include_text=include_text) for p in self.pages],
            "time_seconds": self.time_seconds,
            "phase_timings": self.phase_timings,
        }
        if self.error is not None:
            d["error"] = self.error
        if self.output_path is not None:
            d["output_path"] = self.output_path
        return d


@dataclass
class SignalResult:
    """Result from a quality signal scorer."""

    name: str
    score: float  # 0.0-1.0, higher is better
    passed: bool
    details: dict = field(default_factory=dict)


@dataclass
class BatchResult:
    """Result for an entire batch of files."""

    files: list[FileResult]
    total_time_seconds: float = 0.0
    config: dict = field(default_factory=dict)

    @property
    def success_count(self) -> int:
        """Number of successfully processed files."""
        return sum(1 for f in self.files if f.success)

    @property
    def error_count(self) -> int:
        """Number of files that encountered errors."""
        return sum(1 for f in self.files if not f.success)

    @property
    def flagged_count(self) -> int:
        """Number of files with any flagged pages."""
        return sum(1 for f in self.files if f.flagged_pages)

    def to_dict(self, include_text: bool = False) -> dict:
        """Convert to a JSON-serializable dictionary."""
        return {
            "files": [f.to_dict(include_text=include_text) for f in self.files],
            "total_time_seconds": self.total_time_seconds,
            "config": self.config,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "flagged_count": self.flagged_count,
        }

    def to_json(self, include_text: bool = False, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(include_text=include_text), indent=indent)
