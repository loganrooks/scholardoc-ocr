"""Main OCR pipeline with parallel processing."""

from __future__ import annotations

import logging
import shutil
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from .callbacks import (
    LoggingCallback,
    PhaseEvent,
    PipelineCallback,
    ProgressEvent,
)
from .processor import PDFProcessor, ProcessingResult, ProcessorConfig
from .quality import QualityAnalyzer, QualityResult

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Pipeline configuration."""

    input_dir: Path = field(default_factory=lambda: Path.home() / "Downloads")
    output_dir: Path = field(
        default_factory=lambda: Path.home() / "Downloads" / "scholardoc_ocr"
    )
    quality_threshold: float = 0.85  # Below this, flag for Surya
    force_tesseract: bool = False  # If True, always run Tesseract (skip existing check)
    debug: bool = False  # If True, show sample problem OCR text
    max_samples: int = 20  # Number of problem samples to collect in debug mode
    max_workers: int = 4
    files: list[str] = field(default_factory=list)


@dataclass
class ExtendedResult(ProcessingResult):
    """Extended result with debug info."""
    page_count: int = 0
    file_size_mb: float = 0.0
    quality_details: QualityResult | None = None
    bad_pages: list[int] = field(default_factory=list)  # 0-indexed pages needing Surya
    page_qualities: list[float] = field(default_factory=list)  # Quality score per page
    timings: dict[str, float] = field(default_factory=dict)  # Step timings for debug
    jobs_used: int = 1  # Tesseract threads used


def _process_single(args: tuple) -> ExtendedResult:
    """Process a single PDF with PAGE-LEVEL quality analysis."""
    input_path, output_dir, config_dict = args
    start = time.time()
    timings: dict[str, float] = {}  # Track timing for each step

    # Use more jobs per file if fewer files (better utilization)
    max_workers = config_dict.get("max_workers", 4)
    num_files = config_dict.get("num_files", 1)
    jobs_per_file = max(1, max_workers // max(1, num_files))  # Distribute cores

    config = ProcessorConfig(
        langs_tesseract=config_dict["langs_tesseract"],
        quality_threshold=config_dict["quality_threshold"],
        jobs=jobs_per_file,
    )
    force_tesseract = config_dict.get("force_tesseract", False)
    debug = config_dict.get("debug", False)

    processor = PDFProcessor(config)
    max_samples = config_dict.get("max_samples", 20)
    analyzer = QualityAnalyzer(config.quality_threshold, max_samples=max_samples)

    work_dir = output_dir / "work" / input_path.stem
    work_dir.mkdir(parents=True, exist_ok=True)
    final_dir = output_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    # Get file info
    t0 = time.time()
    file_size_mb = input_path.stat().st_size / (1024 * 1024)
    page_count = processor.get_page_count(input_path)
    timings["file_info"] = time.time() - t0

    try:
        # Step 1: Check existing text PAGE BY PAGE (skip if --force)
        t0 = time.time()
        page_texts = processor.extract_text_by_page(input_path)
        timings["extract_text"] = time.time() - t0

        t0 = time.time()
        page_results = analyzer.analyze_pages(page_texts, collect_context=debug)
        timings["analyze_quality"] = time.time() - t0

        page_qualities = [r.score for r in page_results]
        overall_quality = (
            sum(page_qualities) / len(page_qualities) if page_qualities else 0
        )
        total_words = sum(r.total_words for r in page_results)

        # Check which pages need work
        bad_pages = [i for i, r in enumerate(page_results) if r.flagged]

        if not force_tesseract and not bad_pages:
            # All pages are good - copy as-is
            full_text = "\n\n".join(page_texts)
            text_path = final_dir / f"{input_path.stem}.txt"
            text_path.write_text(full_text, encoding="utf-8")

            pdf_path = final_dir / f"{input_path.stem}.pdf"
            shutil.copy(input_path, pdf_path)

            # Combine issues from all pages for debug
            combined_quality = QualityResult(
                score=overall_quality,
                flagged=False,
                garbled_count=sum(r.garbled_count for r in page_results),
                total_words=total_words,
                sample_issues=[],
                sample_context=[],
            )

            return ExtendedResult(
                filename=input_path.name,
                success=True,
                method="existing",
                quality_score=overall_quality,
                output_text=text_path,
                output_pdf=pdf_path,
                time_seconds=time.time() - start,
                page_count=page_count,
                file_size_mb=file_size_mb,
                quality_details=combined_quality if debug else None,
                bad_pages=[],
                page_qualities=page_qualities,
                timings=timings,
                jobs_used=jobs_per_file,
            )

        # Step 2: Run Tesseract on whole file
        t0 = time.time()
        tess_output = work_dir / f"{input_path.stem}_tesseract.pdf"
        tess_success = processor.run_tesseract(input_path, tess_output)
        timings["tesseract"] = time.time() - t0

        if tess_success:
            # Analyze Tesseract output PAGE BY PAGE
            t0 = time.time()
            tess_page_texts = processor.extract_text_by_page(tess_output)
            timings["tess_extract"] = time.time() - t0

            t0 = time.time()
            tess_page_results = analyzer.analyze_pages(
                tess_page_texts, collect_context=debug
            )
            timings["tess_analyze"] = time.time() - t0

            tess_page_qualities = [r.score for r in tess_page_results]
            tess_overall = (
                sum(tess_page_qualities) / len(tess_page_qualities)
                if tess_page_qualities
                else 0
            )
            tess_total_words = sum(r.total_words for r in tess_page_results)

            # Which pages STILL need Surya after Tesseract?
            bad_pages_after_tess = [
                i for i, r in enumerate(tess_page_results) if r.flagged
            ]

            # Output text and PDF
            full_tess_text = "\n\n".join(tess_page_texts)
            text_path = final_dir / f"{input_path.stem}.txt"
            text_path.write_text(full_tess_text, encoding="utf-8")

            pdf_path = final_dir / f"{input_path.stem}.pdf"
            shutil.copy(tess_output, pdf_path)

            # Combine debug info - show issues from bad pages
            all_issues = []
            all_contexts = []
            for i in bad_pages_after_tess[:5]:  # Limit to first 5 bad pages
                if i < len(tess_page_results):
                    r = tess_page_results[i]
                    for issue in r.sample_issues:
                        all_issues.append(f"[p{i+1}] {issue}")
                    for ctx in r.sample_context:
                        all_contexts.append(f"[p{i+1}] {ctx}")

            combined_quality = QualityResult(
                score=tess_overall,
                flagged=len(bad_pages_after_tess) > 0,
                garbled_count=sum(r.garbled_count for r in tess_page_results),
                total_words=tess_total_words,
                sample_issues=all_issues[:max_samples],
                sample_context=all_contexts[:max_samples],
            )

            if not bad_pages_after_tess:
                return ExtendedResult(
                    filename=input_path.name,
                    success=True,
                    method="tesseract",
                    quality_score=tess_overall,
                    output_text=text_path,
                    output_pdf=pdf_path,
                    time_seconds=time.time() - start,
                    page_count=page_count,
                    file_size_mb=file_size_mb,
                    quality_details=combined_quality if debug else None,
                    bad_pages=[],
                    page_qualities=tess_page_qualities,
                    timings=timings,
                    jobs_used=jobs_per_file,
                )
            else:
                # Some pages still bad - flag for Surya (with page numbers!)
                return ExtendedResult(
                    filename=input_path.name,
                    success=False,
                    method="needs_surya",
                    quality_score=tess_overall,
                    output_text=text_path,
                    output_pdf=pdf_path,
                    error=f"{len(bad_pages_after_tess)} pages below threshold",
                    time_seconds=time.time() - start,
                    page_count=page_count,
                    file_size_mb=file_size_mb,
                    quality_details=combined_quality if debug else None,
                    bad_pages=bad_pages_after_tess,
                    page_qualities=tess_page_qualities,
                    timings=timings,
                    jobs_used=jobs_per_file,
                )

        # Tesseract failed entirely
        return ExtendedResult(
            filename=input_path.name,
            success=False,
            method="error",
            quality_score=0.0,
            error="Tesseract OCR failed",
            time_seconds=time.time() - start,
            page_count=page_count,
            file_size_mb=file_size_mb,
            timings=timings,
            jobs_used=jobs_per_file,
        )

    except Exception as e:
        return ExtendedResult(
            filename=input_path.name,
            success=False,
            method="error",
            quality_score=0.0,
            error=str(e),
            time_seconds=time.time() - start,
            page_count=page_count,
            file_size_mb=file_size_mb,
        )


def run_pipeline(
    config: PipelineConfig,
    callback: PipelineCallback | None = None,
) -> list[ExtendedResult]:
    """Run the OCR pipeline."""
    cb: PipelineCallback = callback or LoggingCallback()
    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "work").mkdir(exist_ok=True)
    (config.output_dir / "final").mkdir(exist_ok=True)

    # Find input files and get info
    input_files: list[Path] = []
    total_pages = 0
    total_size_mb = 0.0

    processor = PDFProcessor()

    for filename in config.files:
        path = config.input_dir / filename
        if path.exists():
            input_files.append(path)
            total_pages += processor.get_page_count(path)
            total_size_mb += path.stat().st_size / (1024 * 1024)
        else:
            logger.warning(f"Not found: {filename}")

    if not input_files:
        logger.warning("No input files found")
        return []

    logger.info(
        "ScholarDoc OCR Pipeline: %d files, ~%d pages, %.1f MB, %d workers",
        len(input_files),
        total_pages,
        total_size_mb,
        config.max_workers,
    )

    # Prepare args
    config_dict = {
        "langs_tesseract": ["eng", "fra", "ell", "lat"],
        "quality_threshold": config.quality_threshold,
        "force_tesseract": config.force_tesseract,
        "debug": config.debug,
        "max_samples": config.max_samples,
        "max_workers": config.max_workers,
        "num_files": len(input_files),
    }
    args_list = [(path, config.output_dir, config_dict) for path in input_files]

    results: list[ExtendedResult] = []
    needs_surya: list[Path] = []

    # Phase 1: Parallel Tesseract
    logger.info(
        "Phase 1: Parallel OCR (Tesseract) - %d workers, %d files, %d pages",
        config.max_workers,
        len(input_files),
        total_pages,
    )

    phase1_start = time.time()
    cb.on_phase(PhaseEvent(
        phase="tesseract", status="started",
        files_count=len(input_files), pages_count=total_pages,
    ))

    completed = 0
    with ProcessPoolExecutor(max_workers=config.max_workers) as executor:
        future_to_path = {}
        for args in args_list:
            future = executor.submit(_process_single, args)
            future_to_path[future] = args[0]

        for future in as_completed(future_to_path):
            path = future_to_path[future]
            try:
                result = future.result()
                results.append(result)
                completed += 1
                cb.on_progress(ProgressEvent(
                    phase="tesseract", current=completed,
                    total=len(input_files), filename=result.filename,
                ))
                logger.info(
                    "%s: %s (%.1f%% quality, %.1fs)",
                    result.filename,
                    result.method,
                    result.quality_score * 100,
                    result.time_seconds,
                )
                if result.method == "needs_surya":
                    needs_surya.append(path)
            except Exception as e:
                logger.error("%s: processing failed: %s", path.name, e)

    phase1_elapsed = time.time() - phase1_start
    logger.info("Phase 1 completed in %.1fs", phase1_elapsed)
    cb.on_phase(PhaseEvent(
        phase="tesseract", status="completed",
        files_count=len(input_files), pages_count=total_pages,
    ))

    # Phase 2: Surya for flagged pages (BATCHED - load models ONCE for all pages)
    if needs_surya:
        # Collect ALL bad pages across ALL files into one list
        all_bad_pages: list[tuple[Path, int, str]] = []
        for r in results:
            if r.method == "needs_surya" and r.bad_pages:
                source_path = config.input_dir / r.filename
                for page_num in r.bad_pages:
                    all_bad_pages.append((source_path, page_num, r.filename))

        total_bad_pages = len(all_bad_pages)
        total_pages_in_flagged = sum(
            r.page_count for r in results if r.method == "needs_surya"
        )

        logger.info(
            "Phase 2: Surya OCR (Batched) - %d files, %d bad pages / %d total",
            len(needs_surya),
            total_bad_pages,
            total_pages_in_flagged,
        )

        cb.on_phase(PhaseEvent(
            phase="surya", status="started",
            files_count=len(needs_surya), pages_count=total_bad_pages,
        ))

        if total_bad_pages > 0:
            surya_start = time.time()
            surya_processor = PDFProcessor()
            work_dir = config.output_dir / "work" / "surya_batch"
            work_dir.mkdir(parents=True, exist_ok=True)

            # Step 1: Combine ALL bad pages from ALL files into ONE PDF
            logger.info(
                "Combining %d pages from %d files",
                total_bad_pages,
                len(needs_surya),
            )
            combined_pdf = work_dir / "all_bad_pages.pdf"
            page_specs = [(path, page_num) for path, page_num, _ in all_bad_pages]

            if surya_processor.combine_pages_from_multiple_pdfs(
                page_specs, combined_pdf
            ):
                size_mb = combined_pdf.stat().st_size / 1024 / 1024
                logger.info("Combined PDF: %.1f MB", size_mb)

                # Step 2: Run Surya
                surya_texts = surya_processor.run_surya_batch(
                    combined_pdf, work_dir, batch_size=50, callback=cb
                )

                if surya_texts:
                    logger.info(
                        "Processed %d pages with Surya", len(surya_texts)
                    )

                    # Step 3: Map Surya results back to original files
                    texts_by_file: dict[str, list[tuple[int, str]]] = defaultdict(
                        list
                    )
                    for i, (_, page_num, filename) in enumerate(all_bad_pages):
                        if i < len(surya_texts):
                            texts_by_file[filename].append(
                                (page_num, surya_texts[i])
                            )

                    # Save updated text files with Surya-improved pages
                    for filename, page_data in texts_by_file.items():
                        text_path = (
                            config.output_dir
                            / "final"
                            / f"{Path(filename).stem}.txt"
                        )
                        if text_path.exists():
                            logger.info(
                                "%s: %d pages enhanced", filename, len(page_data)
                            )
                else:
                    logger.warning(
                        "Surya batch failed, keeping Tesseract output"
                    )

                # Cleanup combined PDF
                combined_pdf.unlink(missing_ok=True)
            else:
                logger.error("Failed to combine pages for Surya")

            surya_elapsed = time.time() - surya_start
            logger.info("Surya phase: %.1fs total", surya_elapsed)

        cb.on_phase(PhaseEvent(
            phase="surya", status="completed",
            files_count=len(needs_surya), pages_count=total_bad_pages,
        ))

    # Summary
    success_count = sum(1 for r in results if r.success)
    surya_count = len(needs_surya)
    error_count = sum(1 for r in results if r.method == "error")

    logger.info(
        "Pipeline complete: %d successful, %d needed Surya, %d errors, output: %s",
        success_count,
        surya_count,
        error_count,
        config.output_dir / "final",
    )

    return results
