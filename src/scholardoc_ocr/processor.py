"""PDF processing with PyMuPDF and ocrmypdf."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

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
    """Process PDFs with PyMuPDF and ocrmypdf."""

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

    def run_tesseract(self, input_path: Path, output_path: Path) -> bool:
        """Run ocrmypdf with Tesseract. Returns True on success."""
        import logging as _logging
        import subprocess
        import sys

        try:
            # Suppress ocrmypdf's logging
            _logging.getLogger("ocrmypdf").setLevel(_logging.CRITICAL)
            _logging.getLogger("PIL").setLevel(_logging.CRITICAL)

            # Build command to run ocrmypdf as subprocess with suppressed output
            cmd = [
                sys.executable, "-m", "ocrmypdf",
                "--redo-ocr",
                "--clean",
                "-l", "+".join(self.config.langs_tesseract),
                "--output-type", "pdfa",
                "--jobs", str(self.config.jobs),
                "--skip-big", "100",
                "--quiet",  # Suppress ocrmypdf's own output
                str(input_path),
                str(output_path),
            ]

            # Run with all output suppressed
            result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=600,  # 10 minute timeout per file
            )

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            logger.error(f"Tesseract OCR timed out for {input_path}")
            return False
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            return False

    def run_surya(self, input_path: Path, output_dir: Path) -> Path | None:
        """Run Marker/Surya OCR. Returns path to markdown output."""
        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict

            # Load models (cached after first call)
            model_dict = create_model_dict()

            converter = PdfConverter(
                artifact_dict=model_dict,
                config={
                    "langs": self.config.langs_surya,
                    "force_ocr": True,
                },
            )

            rendered = converter(str(input_path))

            output_path = output_dir / f"{input_path.stem}.md"
            output_path.write_text(rendered.markdown, encoding="utf-8")

            return output_path

        except ImportError:
            logger.error("Marker not installed. Run: pip install marker-pdf")
            return None
        except Exception as e:
            logger.error(f"Surya OCR failed: {e}")
            return None

    def combine_pages_from_multiple_pdfs(
        self,
        page_specs: list[tuple[Path, int]],
        output_path: Path
    ) -> bool:
        """Combine specific pages from multiple PDFs into one.

        Args:
            page_specs: List of (pdf_path, page_number) tuples, 0-indexed
            output_path: Where to save combined PDF

        Returns:
            True on success
        """
        try:
            with self._open_pdf() as combined:
                for pdf_path, page_num in page_specs:
                    with self._open_pdf(pdf_path) as doc:
                        if 0 <= page_num < len(doc):
                            combined.insert_pdf(doc, from_page=page_num, to_page=page_num)
                combined.save(output_path)
            return True
        except Exception as e:
            logger.error(f"Failed to combine pages: {e}")
            return False

    def run_surya_batch(
        self,
        combined_pdf: Path,
        work_dir: Path,
        batch_size: int = 50,
        progress_callback: Callable[[str, int, int], None] | None = None
    ) -> list[str] | None:
        """Run Surya on a combined PDF, processing in batches.

        Args:
            combined_pdf: PDF containing all pages to OCR
            work_dir: Directory for intermediate files
            batch_size: Pages per batch (to manage memory)
            progress_callback: Optional callback(stage: str, current: int, total: int)

        Returns:
            List of extracted text, one per page in order
        """
        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict

            def report(stage: str, current: int = 0, total: int = 0):
                if progress_callback:
                    progress_callback(stage, current, total)
                else:
                    logger.info(f"{stage}: {current}/{total}" if total else stage)

            # Load models ONCE
            report("Loading Surya models...")
            model_dict = create_model_dict()
            report("Models loaded")

            converter = PdfConverter(
                artifact_dict=model_dict,
                config={
                    "langs": self.config.langs_surya,
                    "force_ocr": True,
                },
            )

            # Get total pages
            total_pages = self.get_page_count(combined_pdf)
            all_texts: list[str] = []
            pages_done = 0

            # Process in batches
            num_batches = (total_pages + batch_size - 1) // batch_size
            for batch_idx, batch_start in enumerate(range(0, total_pages, batch_size)):
                batch_end = min(batch_start + batch_size, total_pages)
                batch_pages = list(range(batch_start, batch_end))
                batch_num = batch_idx + 1

                report(
                    f"Batch {batch_num}/{num_batches}: pages {batch_start+1}-{batch_end}",
                    pages_done,
                    total_pages,
                )

                # Extract batch to temp file
                batch_pdf = work_dir / f"surya_batch_{batch_start}.pdf"
                if not self.extract_pages(combined_pdf, batch_pages, batch_pdf):
                    logger.error(f"Failed to extract batch {batch_start}")
                    pages_done += len(batch_pages)
                    continue

                # Run Surya on batch
                report(f"OCR batch {batch_num}/{num_batches}...", pages_done, total_pages)
                rendered = converter(str(batch_pdf))

                # Extract text per page from markdown
                batch_page_texts = self.extract_text_by_page(batch_pdf)
                if batch_page_texts:
                    all_texts.extend(batch_page_texts)
                else:
                    # Fallback: use markdown as single text
                    all_texts.append(rendered.markdown)

                pages_done += len(batch_pages)
                report(f"Batch {batch_num}/{num_batches} complete", pages_done, total_pages)

                # Cleanup batch file
                batch_pdf.unlink(missing_ok=True)

            report("Surya complete", total_pages, total_pages)
            return all_texts

        except ImportError:
            logger.error("Marker not installed. Run: pip install marker-pdf")
            return None
        except Exception as e:
            logger.error(f"Surya batch OCR failed: {e}")
            return None
