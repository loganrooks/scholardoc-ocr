"""PDF manipulation with PyMuPDF."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import fitz

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    """Result of processing a single PDF."""

    filename: str
    success: bool
    method: str  # "existing", "tesseract", "surya", "error"
    quality_score: float
    output_text: Path | None = None
    output_pdf: Path | None = None
    error: str | None = None
    time_seconds: float = 0.0


@dataclass
class ProcessorConfig:
    """Configuration for PDF processor."""

    langs_tesseract: list[str] = field(default_factory=lambda: ["eng", "fra", "ell", "lat"])
    langs_surya: str = "en,fr,el,la"
    quality_threshold: float = 0.85
    jobs: int = 4


class PDFProcessor:
    """PDF manipulation with PyMuPDF."""

    def __init__(self, config: ProcessorConfig | None = None):
        self.config = config or ProcessorConfig()
        self._fitz: fitz | None = None

    @property
    def fitz(self):
        """Lazy load PyMuPDF."""
        if self._fitz is None:
            import fitz

            self._fitz = fitz
        return self._fitz

    @contextmanager
    def _open_pdf(self, pdf_path: Path | None = None):
        """Context manager for PyMuPDF document. Pass None for empty doc."""
        doc = self.fitz.open(pdf_path) if pdf_path else self.fitz.open()
        try:
            yield doc
        finally:
            doc.close()

    def extract_text(self, pdf_path: Path) -> str:
        """Extract all text from PDF using PyMuPDF (fast, no subprocess)."""
        try:
            with self._open_pdf(pdf_path) as doc:
                text_parts = [page.get_text() for page in doc]
                return "\n".join(text_parts)
        except Exception as e:
            logger.warning(f"Text extraction failed for {pdf_path}: {e}")
            return ""

    def extract_text_by_page(self, pdf_path: Path) -> list[str]:
        """Extract text from each page separately. Returns list of page texts."""
        try:
            with self._open_pdf(pdf_path) as doc:
                return [page.get_text() for page in doc]
        except Exception as e:
            logger.warning(f"Page extraction failed for {pdf_path}: {e}")
            return []

    def extract_pages(self, pdf_path: Path, page_numbers: list[int], output_path: Path) -> bool:
        """Extract specific pages (0-indexed) to a new PDF."""
        try:
            with self._open_pdf(pdf_path) as doc:
                with self._open_pdf() as new_doc:
                    for page_num in page_numbers:
                        if 0 <= page_num < len(doc):
                            new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                    new_doc.save(output_path)
            return True
        except Exception as e:
            logger.error(f"Failed to extract pages {page_numbers}: {e}")
            return False

    def replace_pages(self, original_path: Path, replacement_path: Path,
                      page_numbers: list[int], output_path: Path) -> bool:
        """Replace specific pages in original with pages from replacement PDF.

        Args:
            original_path: The original PDF
            replacement_path: PDF containing replacement pages (in order matching page_numbers)
            page_numbers: Which pages (0-indexed) in original to replace
            output_path: Where to save the merged result
        """
        try:
            with self._open_pdf(original_path) as original:
                with self._open_pdf(replacement_path) as replacement:
                    with self._open_pdf() as result:
                        replacement_idx = 0
                        for page_num in range(len(original)):
                            if page_num in page_numbers and replacement_idx < len(replacement):
                                result.insert_pdf(
                                    replacement,
                                    from_page=replacement_idx,
                                    to_page=replacement_idx,
                                )
                                replacement_idx += 1
                            else:
                                result.insert_pdf(
                                    original, from_page=page_num, to_page=page_num
                                )
                        result.save(output_path)
            return True
        except Exception as e:
            logger.error(f"Failed to replace pages: {e}")
            return False

    def get_page_count(self, pdf_path: Path) -> int:
        """Get page count using PyMuPDF."""
        try:
            with self._open_pdf(pdf_path) as doc:
                return len(doc)
        except Exception:
            return 0

