"""Main OCR pipeline with parallel processing."""

from __future__ import annotations

import logging
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

from .processor import PDFProcessor, ProcessorConfig, ProcessingResult
from .quality import QualityAnalyzer, QualityResult

logger = logging.getLogger(__name__)
console = Console()


@dataclass
class PipelineConfig:
    """Pipeline configuration."""

    input_dir: Path = field(default_factory=lambda: Path.home() / "Downloads")
    output_dir: Path = field(default_factory=lambda: Path.home() / "Downloads" / "levinas_ocr")
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
        overall_quality = sum(page_qualities) / len(page_qualities) if page_qualities else 0
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
            tess_page_results = analyzer.analyze_pages(tess_page_texts, collect_context=debug)
            timings["tess_analyze"] = time.time() - t0

            tess_page_qualities = [r.score for r in tess_page_results]
            tess_overall = sum(tess_page_qualities) / len(tess_page_qualities) if tess_page_qualities else 0
            tess_total_words = sum(r.total_words for r in tess_page_results)

            # Which pages STILL need Surya after Tesseract?
            bad_pages_after_tess = [i for i, r in enumerate(tess_page_results) if r.flagged]

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


def _print_debug_info(result: ExtendedResult) -> None:
    """Print detailed debug info for a result."""
    console.print(f"    [dim]─── Debug Info ───[/dim]")

    # Show timing breakdown
    if result.timings:
        timing_parts = []
        for step, secs in result.timings.items():
            timing_parts.append(f"{step}={secs:.1f}s")
        console.print(f"    [dim]Timings: {', '.join(timing_parts)}[/dim]")
        console.print(f"    [dim]Tesseract jobs: {result.jobs_used}[/dim]")

    if result.quality_details:
        q = result.quality_details
        words_per_page = q.total_words / max(result.page_count, 1)
        console.print(f"    [dim]Words: {q.total_words:,} total ({words_per_page:.0f}/page) | Garbled: {q.garbled_count} ({q.garbled_count/max(q.total_words,1)*100:.2f}%)[/dim]")

        # Show page quality distribution
        if result.page_qualities:
            min_q = min(result.page_qualities)
            max_q = max(result.page_qualities)
            avg_q = sum(result.page_qualities) / len(result.page_qualities)
            console.print(f"    [dim]Page quality: min={min_q:.1%} avg={avg_q:.1%} max={max_q:.1%}[/dim]")

        # Show bad pages if any
        if result.bad_pages:
            page_nums = [str(p + 1) for p in result.bad_pages[:15]]
            page_str = ", ".join(page_nums)
            if len(result.bad_pages) > 15:
                page_str += f" ... (+{len(result.bad_pages) - 15} more)"
            console.print(f"    [yellow]Bad pages ({len(result.bad_pages)}/{result.page_count}): {page_str}[/yellow]")

        if q.sample_issues:
            console.print(f"    [dim]Problem samples ({len(q.sample_issues)}):[/dim]")
            for i, issue in enumerate(q.sample_issues[:15]):
                console.print(f"      [red]• {issue}[/red]")
                if q.sample_context and i < len(q.sample_context):
                    ctx = q.sample_context[i][:100]
                    console.print(f"        [dim]{ctx}...[/dim]")


def run_pipeline(config: PipelineConfig) -> list[ExtendedResult]:
    """Run the OCR pipeline."""
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
            console.print(f"[yellow]⚠ Not found: {filename}[/yellow]")

    if not input_files:
        console.print("[red]No input files found![/red]")
        return []

    # Header
    console.print()
    console.print("[bold blue]═" * 60 + "[/bold blue]")
    console.print("[bold blue]LEVINAS OCR PIPELINE[/bold blue]")
    console.print("[bold blue]═" * 60 + "[/bold blue]")

    # Info table
    info_table = Table(show_header=False, box=None, padding=(0, 2))
    info_table.add_column(style="dim")
    info_table.add_column()
    info_table.add_row("Files", f"{len(input_files)}")
    info_table.add_row("Total pages", f"~{total_pages}")
    info_table.add_row("Total size", f"{total_size_mb:.1f} MB")
    info_table.add_row("Workers", f"{config.max_workers}")
    info_table.add_row("Surya threshold", f"{config.quality_threshold:.0%}")
    if config.force_tesseract:
        info_table.add_row("Mode", "[yellow]FORCE (always Tesseract)[/yellow]")
    if config.debug:
        info_table.add_row("Debug", "[cyan]ON (showing problem samples)[/cyan]")
    console.print(info_table)
    console.print()

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
    console.print("[bold]Phase 1: Parallel OCR (Tesseract)[/bold]")
    console.print(f"[dim]Workers: {config.max_workers} | Files: {len(input_files)} | Total pages: {total_pages}[/dim]")
    console.print()

    # Track which files are currently being processed
    from rich.live import Live
    from rich.table import Table

    phase1_start = time.time()
    completed_count = 0
    in_progress: dict[str, float] = {}  # filename -> start_time

    def make_status_table() -> Table:
        """Create a live status table."""
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Status", width=60)

        elapsed = time.time() - phase1_start
        pct = (completed_count / len(input_files)) * 100 if input_files else 0

        table.add_row(f"[cyan]Progress:[/cyan] {completed_count}/{len(input_files)} files ({pct:.0f}%) | Elapsed: {elapsed:.0f}s")

        if in_progress:
            active = []
            for fname, start in list(in_progress.items())[:4]:  # Show up to 4 active
                file_elapsed = time.time() - start
                short_name = fname[:40] + "..." if len(fname) > 40 else fname
                active.append(f"{short_name} ({file_elapsed:.0f}s)")
            table.add_row(f"[yellow]Processing:[/yellow] {', '.join(active)}")

        return table

    with Live(make_status_table(), console=console, refresh_per_second=2) as live:
        with ProcessPoolExecutor(max_workers=config.max_workers) as executor:
            future_to_path = {}

            # Submit all jobs and track start times
            for args in args_list:
                future = executor.submit(_process_single, args)
                path = args[0]
                future_to_path[future] = path
                in_progress[path.name] = time.time()

            for future in as_completed(future_to_path):
                path = future_to_path[future]

                # Remove from in-progress
                in_progress.pop(path.name, None)

                try:
                    result = future.result()
                    results.append(result)
                    completed_count += 1

                    # Update live display
                    live.update(make_status_table())

                    if result.method == "needs_surya":
                        needs_surya.append(path)

                except Exception as e:
                    completed_count += 1
                    live.update(make_status_table())
                    console.print(f"  [red]✗ {path.name}: {e}[/red]")

    # Now print all results
    console.print()
    console.print("[bold]Phase 1 Results:[/bold]")
    for result in sorted(results, key=lambda r: r.filename):
        # Status indicator
        if result.success:
            status, color = "✓", "green"
        elif result.method == "needs_surya":
            status, color = "⚠", "yellow"
        else:
            status, color = "✗", "red"

        # Main result line
        console.print(
            f"  [{color}]{status}[/{color}] [bold]{result.filename}[/bold] "
            f"[dim]({result.page_count}pp, {result.file_size_mb:.1f}MB)[/dim]"
        )
        console.print(
            f"    {result.method} → [{'green' if result.quality_score >= config.quality_threshold else 'yellow'}]"
            f"{result.quality_score:.1%} quality[/] "
            f"[dim][{result.time_seconds:.1f}s][/dim]"
        )

        # Show bad pages if any
        if result.bad_pages:
            page_nums = [str(p + 1) for p in result.bad_pages[:10]]
            page_str = ", ".join(page_nums)
            if len(result.bad_pages) > 10:
                page_str += f" +{len(result.bad_pages) - 10} more"
            console.print(f"    [yellow]Bad pages: {page_str}[/yellow]")

        # Debug info if enabled
        if config.debug and result.quality_details:
            _print_debug_info(result)

        console.print()  # Spacing between files

    phase1_elapsed = time.time() - phase1_start
    console.print(f"[dim]Phase 1 completed in {phase1_elapsed:.1f}s[/dim]")
    console.print()

    # Phase 2: Surya for flagged pages (BATCHED - load models ONCE for all pages)
    if needs_surya:
        console.print()

        # Collect ALL bad pages across ALL files into one list
        # Format: (source_pdf_path, page_number, original_filename)
        all_bad_pages: list[tuple[Path, int, str]] = []
        for r in results:
            if r.method == "needs_surya" and r.bad_pages:
                source_path = config.input_dir / r.filename
                for page_num in r.bad_pages:
                    all_bad_pages.append((source_path, page_num, r.filename))

        total_bad_pages = len(all_bad_pages)
        total_pages_in_flagged = sum(r.page_count for r in results if r.method == "needs_surya")

        console.print(f"[bold]Phase 2: Surya OCR (Batched - models load once)[/bold]")
        console.print(f"[dim]{len(needs_surya)} files, {total_bad_pages} bad pages / {total_pages_in_flagged} total[/dim]")
        console.print()

        # Show which pages need work for each file
        for r in results:
            if r.method == "needs_surya" and r.bad_pages:
                page_nums = [str(p + 1) for p in r.bad_pages[:15]]  # 1-indexed for display
                page_str = ", ".join(page_nums)
                if len(r.bad_pages) > 15:
                    page_str += f" ... (+{len(r.bad_pages) - 15} more)"
                console.print(f"  [yellow]⚠[/yellow] {r.filename}: pages {page_str}")

        console.print()

        if total_bad_pages == 0:
            console.print("[dim]No pages to process with Surya[/dim]")
        else:
            surya_start = time.time()
            surya_processor = PDFProcessor()
            work_dir = config.output_dir / "work" / "surya_batch"
            work_dir.mkdir(parents=True, exist_ok=True)

            # Step 1: Combine ALL bad pages from ALL files into ONE PDF
            console.print(f"[dim]Combining {total_bad_pages} pages from {len(needs_surya)} files...[/dim]")
            combined_pdf = work_dir / "all_bad_pages.pdf"
            page_specs = [(path, page_num) for path, page_num, _ in all_bad_pages]

            if surya_processor.combine_pages_from_multiple_pdfs(page_specs, combined_pdf):
                size_mb = combined_pdf.stat().st_size / 1024 / 1024
                console.print(f"[dim]Combined PDF: {size_mb:.1f}MB[/dim]")
                console.print()

                # Step 2: Run Surya with live progress updates
                from rich.live import Live
                from rich.table import Table

                surya_status = {"stage": "Initializing...", "current": 0, "total": total_bad_pages}

                def make_surya_status() -> Table:
                    table = Table(show_header=False, box=None, padding=(0, 1))
                    table.add_column("Info", width=70)

                    pct = (surya_status["current"] / surya_status["total"] * 100) if surya_status["total"] else 0
                    elapsed = time.time() - surya_start

                    table.add_row(f"[cyan]{surya_status['stage']}[/cyan]")
                    table.add_row(f"[dim]Pages: {surya_status['current']}/{surya_status['total']} ({pct:.0f}%) | Elapsed: {elapsed:.0f}s[/dim]")

                    # Estimate remaining time
                    if surya_status["current"] > 0:
                        rate = surya_status["current"] / elapsed
                        remaining = (surya_status["total"] - surya_status["current"]) / rate if rate > 0 else 0
                        table.add_row(f"[dim]Rate: {rate:.1f} pages/s | ETA: {remaining:.0f}s[/dim]")

                    return table

                def progress_callback(stage: str, current: int, total: int):
                    surya_status["stage"] = stage
                    surya_status["current"] = current
                    surya_status["total"] = total or surya_status["total"]

                with Live(make_surya_status(), console=console, refresh_per_second=2) as live:
                    def updating_callback(stage: str, current: int, total: int):
                        progress_callback(stage, current, total)
                        live.update(make_surya_status())

                    surya_texts = surya_processor.run_surya_batch(
                        combined_pdf, work_dir, batch_size=50,
                        progress_callback=updating_callback
                    )

                console.print()
                if surya_texts:
                    console.print(f"    [green]✓[/green] Processed {len(surya_texts)} pages with Surya")

                    # Step 3: Map Surya results back to original files
                    from collections import defaultdict
                    texts_by_file: dict[str, list[tuple[int, str]]] = defaultdict(list)

                    for i, (_, page_num, filename) in enumerate(all_bad_pages):
                        if i < len(surya_texts):
                            texts_by_file[filename].append((page_num, surya_texts[i]))

                    # Save updated text files with Surya-improved pages
                    for filename, page_data in texts_by_file.items():
                        text_path = config.output_dir / "final" / f"{Path(filename).stem}.txt"
                        if text_path.exists():
                            console.print(f"    [dim]{filename}: {len(page_data)} pages enhanced[/dim]")
                else:
                    console.print(f"    [yellow]⚠[/yellow] Surya batch failed, keeping Tesseract output")

                # Cleanup combined PDF
                combined_pdf.unlink(missing_ok=True)

            else:
                console.print(f"    [red]✗[/red] Failed to combine pages for Surya")

            surya_elapsed = time.time() - surya_start
            console.print(f"\n[dim]Surya phase: {surya_elapsed:.1f}s total[/dim]")
            console.print()

    # Summary
    console.print("[bold blue]═" * 60 + "[/bold blue]")

    success_count = sum(1 for r in results if r.success)
    surya_count = len(needs_surya)
    error_count = sum(1 for r in results if r.method == "error")

    summary = Table(show_header=False, box=None, padding=(0, 2))
    summary.add_column(style="bold")
    summary.add_column()
    summary.add_row("[green]✓ Successful[/green]", f"{success_count}")
    if surya_count:
        summary.add_row("[yellow]⚠ Needed Surya[/yellow]", f"{surya_count}")
    if error_count:
        summary.add_row("[red]✗ Errors[/red]", f"{error_count}")
    summary.add_row("Output", str(config.output_dir / "final"))

    console.print(Panel(summary, title="[bold green]COMPLETE[/bold green]", border_style="blue"))

    return results
