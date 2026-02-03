"""Main OCR pipeline with parallel Tesseract and per-file Surya fallback."""

from __future__ import annotations

import logging
import os
import shutil
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from .callbacks import (
    LoggingCallback,
    ModelEvent,
    PhaseEvent,
    PipelineCallback,
    ProgressEvent,
)
from .types import BatchResult, FileResult, OCREngine, PageResult, PageStatus

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """Pipeline configuration."""

    input_dir: Path = field(default_factory=lambda: Path.home() / "Downloads")
    output_dir: Path = field(
        default_factory=lambda: Path.home() / "Downloads" / "scholardoc_ocr"
    )
    quality_threshold: float = 0.85
    force_tesseract: bool = False
    force_surya: bool = False
    debug: bool = False
    max_samples: int = 20
    max_workers: int = 4
    files: list[str] = field(default_factory=list)
    langs_tesseract: str = "eng,fra,ell,lat,deu"
    langs_surya: str = "en,fr,el,la,de"
    keep_intermediates: bool = False
    timeout: int = 1800


def _tesseract_worker(
    input_path: Path, output_dir: Path, config_dict: dict
) -> FileResult:
    """Process a single PDF with Tesseract in a worker process.

    This is a top-level function accepting only picklable args.
    It must NOT import surya.
    """
    from .postprocess import postprocess
    from .processor import PDFProcessor
    from .quality import QualityAnalyzer
    from .tesseract import TesseractConfig, run_ocr

    start = time.time()
    timings: dict[str, float] = {}

    threshold = config_dict["quality_threshold"]
    force_tesseract = config_dict.get("force_tesseract", False)
    jobs_per_file = config_dict.get("jobs_per_file", 1)

    processor = PDFProcessor()
    analyzer = QualityAnalyzer(threshold, max_samples=config_dict.get("max_samples", 20))

    work_dir = output_dir / "work" / input_path.stem
    work_dir.mkdir(parents=True, exist_ok=True)
    final_dir = output_dir / "final"
    final_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Extract existing text page-by-page
        t0 = time.time()
        page_texts = processor.extract_text_by_page(input_path)
        timings["extract_text"] = time.time() - t0
        page_count = len(page_texts) or processor.get_page_count(input_path)

        # Analyze quality
        t0 = time.time()
        page_results = analyzer.analyze_pages(page_texts)
        timings["analyze_quality"] = time.time() - t0

        page_qualities = [r.score for r in page_results]
        overall_quality = (
            sum(page_qualities) / len(page_qualities) if page_qualities else 0.0
        )
        bad_pages = [i for i, r in enumerate(page_results) if r.flagged]

        # If existing text is good enough and not forced, use as-is
        if not force_tesseract and not bad_pages:
            full_text = postprocess("\n\n".join(page_texts))
            text_path = final_dir / f"{input_path.stem}.txt"
            text_path.write_text(full_text, encoding="utf-8")
            pdf_path = final_dir / f"{input_path.stem}.pdf"
            shutil.copy(input_path, pdf_path)

            pages = [
                PageResult(
                    page_number=i,
                    status=PageStatus.GOOD,
                    quality_score=page_qualities[i] if i < len(page_qualities) else 0.0,
                    engine=OCREngine.EXISTING,
                    flagged=False,
                    text=page_texts[i] if i < len(page_texts) else None,
                )
                for i in range(page_count)
            ]
            return FileResult(
                filename=input_path.name,
                success=True,
                engine=OCREngine.EXISTING,
                quality_score=overall_quality,
                page_count=page_count,
                pages=pages,
                time_seconds=time.time() - start,
                phase_timings=timings,
                output_path=str(pdf_path),
            )

        # Run Tesseract
        t0 = time.time()
        tess_output = work_dir / f"{input_path.stem}_tesseract.pdf"
        tess_config = TesseractConfig(
            langs=config_dict.get("langs_tesseract", ["eng", "fra", "ell", "lat"]),
            jobs=jobs_per_file,
        )
        tess_result = run_ocr(input_path, tess_output, tess_config)
        timings["tesseract"] = time.time() - t0

        if not tess_result.success:
            return FileResult(
                filename=input_path.name,
                success=False,
                engine=OCREngine.TESSERACT,
                quality_score=0.0,
                page_count=page_count,
                pages=[],
                error=(
                    tess_result.error or "Tesseract OCR failed (no details)"
                ),
                time_seconds=time.time() - start,
                phase_timings=timings,
            )

        # Re-extract and re-analyze after Tesseract
        t0 = time.time()
        tess_page_texts = processor.extract_text_by_page(tess_output)
        timings["tess_extract"] = time.time() - t0

        t0 = time.time()
        tess_page_results = analyzer.analyze_pages(tess_page_texts)
        timings["tess_analyze"] = time.time() - t0

        tess_qualities = [r.score for r in tess_page_results]
        tess_overall = (
            sum(tess_qualities) / len(tess_qualities) if tess_qualities else 0.0
        )
        bad_after_tess = [i for i, r in enumerate(tess_page_results) if r.flagged]

        # Write Tesseract output
        full_text = postprocess("\n\n".join(tess_page_texts))
        text_path = final_dir / f"{input_path.stem}.txt"
        text_path.write_text(full_text, encoding="utf-8")
        pdf_path = final_dir / f"{input_path.stem}.pdf"
        shutil.copy(tess_output, pdf_path)

        pages = [
            PageResult(
                page_number=i,
                status=PageStatus.FLAGGED if i in bad_after_tess else PageStatus.GOOD,
                quality_score=tess_qualities[i] if i < len(tess_qualities) else 0.0,
                engine=OCREngine.TESSERACT,
                flagged=i in bad_after_tess,
                text=tess_page_texts[i] if i < len(tess_page_texts) else None,
            )
            for i in range(page_count)
        ]

        return FileResult(
            filename=input_path.name,
            success=True,
            engine=OCREngine.TESSERACT,
            quality_score=tess_overall,
            page_count=page_count,
            pages=pages,
            time_seconds=time.time() - start,
            phase_timings=timings,
            output_path=str(pdf_path),
        )

    except Exception as e:
        logger.error("%s: Tesseract worker failed: %s", input_path.name, e, exc_info=True)
        return FileResult(
            filename=input_path.name,
            success=False,
            engine=OCREngine.NONE,
            quality_score=0.0,
            page_count=0,
            pages=[],
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            time_seconds=time.time() - start,
            phase_timings=timings,
        )


def run_pipeline(
    config: PipelineConfig,
    callback: PipelineCallback | None = None,
) -> BatchResult:
    """Run the OCR pipeline.

    Phase 1: Parallel Tesseract OCR with resource-aware worker count.
    Phase 2: Sequential per-file Surya on flagged pages with shared models.

    Returns:
        BatchResult with per-file and per-page details.
    """
    from . import surya
    from .logging_ import setup_main_logging, stop_logging, worker_log_initializer
    from .postprocess import postprocess as _postprocess

    cb: PipelineCallback = callback or LoggingCallback()
    pipeline_start = time.time()

    config.output_dir.mkdir(parents=True, exist_ok=True)
    (config.output_dir / "work").mkdir(exist_ok=True)
    (config.output_dir / "final").mkdir(exist_ok=True)

    # Set up queue-based logging for worker processes
    log_dir = config.output_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_queue, log_listener = setup_main_logging(log_dir=log_dir, verbose=config.debug)

    try:
        # --- File discovery ---
        input_files: list[Path] = []
        if config.files:
            for filename in config.files:
                path = config.input_dir / filename
                if path.exists():
                    input_files.append(path)
                else:
                    logger.warning("Not found: %s", filename)
        elif config.input_dir.is_dir():
            input_files = sorted(config.input_dir.glob("*.pdf"))

        if not input_files:
            logger.warning("No input files found")
            return BatchResult(files=[], total_time_seconds=0.0)

        # --- Resource-aware worker calculation ---
        total_cores = os.cpu_count() or 4
        num_files = len(input_files)
        jobs_per_file = max(1, total_cores // max(1, num_files))
        pool_workers = max(1, min(config.max_workers, total_cores // jobs_per_file))

        logger.info(
            "Pipeline: %d files, %d pool workers, %d jobs/file",
            num_files, pool_workers, jobs_per_file,
        )

        # Prepare config dict (picklable)
        config_dict = {
            "langs_tesseract": config.langs_tesseract.split(","),
            "langs_surya": config.langs_surya.split(","),
            "quality_threshold": config.quality_threshold,
            "force_tesseract": config.force_tesseract,
            "debug": config.debug,
            "max_samples": config.max_samples,
            "jobs_per_file": jobs_per_file,
        }

        # --- Phase 1: Parallel Tesseract ---
        cb.on_phase(PhaseEvent(
            phase="tesseract", status="started",
            files_count=num_files, pages_count=0,
        ))

        file_results: list[FileResult] = []
        completed = 0

        with ProcessPoolExecutor(
            max_workers=pool_workers,
            initializer=worker_log_initializer,
            initargs=(log_queue, log_dir),
        ) as executor:
            future_to_path = {}
            for path in input_files:
                future = executor.submit(
                    _tesseract_worker, path, config.output_dir, config_dict
                )
                future_to_path[future] = path

            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    result = future.result(timeout=config.timeout)
                    file_results.append(result)
                    completed += 1
                    cb.on_progress(ProgressEvent(
                        phase="tesseract", current=completed,
                        total=num_files, filename=result.filename,
                    ))
                    logger.info(
                        "%s: %s (%.1f%% quality, %.1fs)",
                        result.filename, result.engine,
                        result.quality_score * 100, result.time_seconds,
                    )
                except TimeoutError:
                    logger.error(
                        "%s: timed out after %ds", path.name, config.timeout
                    )
                    file_results.append(FileResult(
                        filename=path.name,
                        success=False,
                        engine=OCREngine.NONE,
                        quality_score=0.0,
                        page_count=0,
                        pages=[],
                        error=f"Timed out after {config.timeout}s",
                    ))
                except Exception as e:
                    logger.error(
                        "%s: worker failed: %s", path.name, e, exc_info=True
                    )
                    file_results.append(FileResult(
                        filename=path.name,
                        success=False,
                        engine=OCREngine.NONE,
                        quality_score=0.0,
                        page_count=0,
                        pages=[],
                        error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
                    ))

        cb.on_phase(PhaseEvent(
            phase="tesseract", status="completed",
            files_count=num_files, pages_count=0,
        ))

        # --- Phase 2: Sequential per-file Surya ---
        flagged_results = [
            r for r in file_results
            if config.force_surya or r.flagged_pages
        ]

        if flagged_results:
            total_flagged_pages = sum(
                len(r.flagged_pages) for r in flagged_results
            )
            logger.info(
                "Phase 2: Surya OCR — %d files, %d flagged pages",
                len(flagged_results), total_flagged_pages,
            )

            cb.on_phase(PhaseEvent(
                phase="surya", status="started",
                files_count=len(flagged_results),
                pages_count=total_flagged_pages,
            ))

            # Load models once
            cb.on_model(ModelEvent(model_name="surya", status="loading"))
            t0 = time.time()
            model_dict = surya.load_models()
            model_time = time.time() - t0
            cb.on_model(ModelEvent(
                model_name="surya", status="loaded", time_seconds=model_time
            ))

            surya_completed = 0
            for file_result in flagged_results:
                try:
                    input_path = config.input_dir / file_result.filename
                    if not input_path.exists():
                        # Try files list directly
                        input_path = next(
                            (p for p in input_files if p.name == file_result.filename),
                            None,
                        )
                        if input_path is None:
                            logger.warning(
                                "Cannot find source for Surya: %s",
                                file_result.filename,
                            )
                            continue

                    # Get flagged page indices
                    if config.force_surya:
                        bad_indices = list(range(file_result.page_count))
                    else:
                        bad_indices = [
                            p.page_number for p in file_result.flagged_pages
                        ]

                    if not bad_indices:
                        continue

                    logger.info(
                        "%s: running Surya on %d pages %s",
                        file_result.filename, len(bad_indices), bad_indices,
                    )

                    # Convert with Surya
                    from .surya import SuryaConfig

                    surya_cfg = SuryaConfig(langs=config.langs_surya)
                    surya_markdown = surya.convert_pdf(
                        input_path, model_dict, config=surya_cfg,
                        page_range=bad_indices,
                    )

                    # Write Surya text back to output .txt file
                    text_path = (
                        config.output_dir / "final" / f"{input_path.stem}.txt"
                    )
                    if text_path.exists():
                        existing_text = text_path.read_text(encoding="utf-8")
                        page_texts = existing_text.split("\n\n")

                        for idx, page_num in enumerate(bad_indices):
                            if page_num < len(page_texts):
                                if idx == 0:
                                    page_texts[page_num] = surya_markdown
                                else:
                                    page_texts[page_num] = ""

                        text_path.write_text(
                            _postprocess("\n\n".join(page_texts)), encoding="utf-8"
                        )

                    # Update PageResult entries for enhanced pages
                    for page in file_result.pages:
                        if page.page_number in bad_indices:
                            page.engine = OCREngine.SURYA
                            page.status = PageStatus.GOOD
                            page.flagged = False

                    surya_completed += 1
                    cb.on_progress(ProgressEvent(
                        phase="surya", current=surya_completed,
                        total=len(flagged_results),
                        filename=file_result.filename,
                    ))
                    logger.info(
                        "%s: Surya enhancement complete", file_result.filename
                    )

                except Exception as e:
                    logger.warning(
                        "%s: Surya failed, keeping Tesseract output: %s",
                        file_result.filename, e, exc_info=True,
                    )

            cb.on_phase(PhaseEvent(
                phase="surya", status="completed",
                files_count=len(flagged_results),
                pages_count=total_flagged_pages,
            ))

        # --- Cleanup work directory ---
        work_dir = config.output_dir / "work"
        if work_dir.exists() and not config.keep_intermediates:
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.info("Cleaned up work directory")
        elif config.keep_intermediates:
            logger.info("Keeping work directory: %s", work_dir)

        elapsed = time.time() - pipeline_start
        success_count = sum(1 for r in file_results if r.success)
        logger.info(
            "Pipeline complete: %d/%d successful in %.1fs, output: %s",
            success_count, len(file_results), elapsed,
            config.output_dir / "final",
        )

        return BatchResult(
            files=file_results,
            total_time_seconds=elapsed,
            config={
                "quality_threshold": config.quality_threshold,
                "force_tesseract": config.force_tesseract,
                "force_surya": config.force_surya,
                "max_workers": config.max_workers,
            },
        )
    finally:
        stop_logging(log_listener)
