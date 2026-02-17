"""Command-line interface with Rich progress display."""

from __future__ import annotations

import argparse
import logging
import multiprocessing as mp
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

from .callbacks import ModelEvent, PhaseEvent, ProgressEvent
from .pipeline import PipelineConfig, run_pipeline
from .types import BatchResult, OCREngine, resolve_languages


class RichCallback:
    """Pipeline callback that renders Rich progress bars and status messages."""

    def __init__(self, console: Console) -> None:
        self._console = console
        self._progress: Progress | None = None
        self._task_id = None

    def on_phase(self, event: PhaseEvent) -> None:
        """Handle phase lifecycle events."""
        try:
            if event.status == "started":
                self._progress = Progress(
                    SpinnerColumn(),
                    TextColumn("[bold blue]{task.description}"),
                    BarColumn(),
                    TaskProgressColumn(),
                    TimeRemainingColumn(),
                    console=self._console,
                )
                self._progress.start()
                self._task_id = self._progress.add_task(f"{event.phase}", total=event.files_count)
            elif event.status == "completed":
                if self._progress is not None:
                    self._progress.stop()
                    self._progress = None
                    self._task_id = None
        except Exception:
            print(f"Phase {event.phase}: {event.status}")

    def on_progress(self, event: ProgressEvent) -> None:
        """Update progress bar with current file."""
        try:
            if self._progress is not None and self._task_id is not None:
                desc = f"{event.phase}: {event.filename or ''}"
                self._progress.update(self._task_id, completed=event.current, description=desc)
        except Exception:
            print(f"{event.phase}: {event.current}/{event.total} {event.filename or ''}")

    def on_model(self, event: ModelEvent) -> None:
        """Display model loading status."""
        try:
            if event.status == "loading":
                self._console.print(f"[yellow]Loading {event.model_name} models...[/]")
            elif event.status == "loaded":
                self._console.print(
                    f"[green]{event.model_name} models loaded ({event.time_seconds:.1f}s)[/]"
                )
        except Exception:
            msg = f"Model {event.model_name}: {event.status}"
            if event.time_seconds is not None:
                msg += f" ({event.time_seconds:.1f}s)"
            print(msg)


def _print_summary(
    console: Console,
    batch: BatchResult,
    output_dir: Path,
    quality_threshold: float,
    debug: bool = False,
) -> None:
    """Print a Rich table summary of the batch result."""
    table = Table(title="OCR Pipeline Summary")
    table.add_column("Filename", style="cyan", no_wrap=True)
    table.add_column("Pages", justify="right")
    table.add_column("Quality", justify="right")
    table.add_column("Engine")
    table.add_column("Time", justify="right")

    for f in batch.files:
        if f.success:
            q_style = "green" if f.quality_score >= quality_threshold else "yellow"
            table.add_row(
                f.filename,
                str(f.page_count),
                f"[{q_style}]{f.quality_score:.1%}[/{q_style}]",
                str(f.engine),
                f"{f.time_seconds:.1f}s",
            )
        else:
            table.add_row(
                f.filename,
                "-",
                "[red]ERROR[/red]",
                "-",
                f.error or "Unknown error",
            )

    console.print()
    console.print(table)
    console.print()
    console.print(
        f"  Total files: {len(batch.files)}  |  "
        f"Successful: {batch.success_count}  |  "
        f"Errors: {batch.error_count}  |  "
        f"Total time: {batch.total_time_seconds:.1f}s"
    )
    console.print(f"  Output: {output_dir / 'final'}")
    console.print()

    if debug:
        flagged_files = [f for f in batch.files if f.flagged_pages]
        if flagged_files:
            console.print("[bold]Flagged Page Details:[/bold]")
            for f in flagged_files:
                console.print(f"  [cyan]{f.filename}[/cyan]:")
                for p in f.pages:
                    if p.flagged or p.engine == OCREngine.SURYA:
                        console.print(
                            f"    Page {p.page_number:>3}: "
                            f"quality={p.quality_score:.1%}  engine={p.engine}"
                        )
            console.print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="High-performance OCR for academic texts (Apple Silicon optimized)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ocr ~/Dropbox/scans        # Process all PDFs in a folder
  ocr . -o ./output          # Current dir, custom output
  ocr ~/Downloads            # Process ~/Downloads folder
  ocr --quality 0.9          # Higher quality threshold (more Surya)
  ocr --force                # Force Tesseract re-OCR on all files
  ocr --force-surya          # Force Surya OCR on all pages
  ocr --debug                # Show sample problem OCR text
  ocr -f file1.pdf file2.pdf # Process specific files only
  ocr -l en,de               # English and German only
        """,
    )

    parser.add_argument(
        "input_dir",
        nargs="?",
        default=".",
        help="Input directory containing PDFs (default: current directory)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Output directory (default: <input_dir>/ocr_output)",
    )
    parser.add_argument(
        "-q",
        "--quality",
        type=float,
        default=0.85,
        help="Quality threshold 0-1 (default: 0.85). Below this, flag for Surya.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force Tesseract re-OCR on all files (skip existing text check).",
    )
    parser.add_argument(
        "--force-surya",
        action="store_true",
        help="Force Surya OCR on all pages regardless of quality.",
    )
    parser.add_argument(
        "--strict-gpu",
        action="store_true",
        help="Fail if GPU (MPS/CUDA) unavailable instead of falling back to CPU.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show detailed quality analysis with sample problem text.",
    )
    parser.add_argument(
        "-s",
        "--samples",
        type=int,
        default=20,
        help="Number of problem samples to show in debug mode (default: 20)",
    )
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=mp.cpu_count(),
        help=f"Parallel workers (default: {mp.cpu_count()})",
    )
    parser.add_argument(
        "-f",
        "--files",
        nargs="+",
        help="Specific PDF files to process (instead of all PDFs in input_dir)",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recursively search subdirectories for PDFs",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging",
    )
    parser.add_argument(
        "-l",
        "--language",
        default="en,fr,el,la,de",
        help="Comma-separated ISO 639-1 language codes (default: en,fr,el,la,de)",
    )
    parser.add_argument(
        "--keep-intermediates",
        action="store_true",
        help="Keep work directory for debugging",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Per-file timeout in seconds (default: 1800)",
    )
    parser.add_argument(
        "--extract-text",
        action="store_true",
        help="Write post-processed .txt file alongside output PDF",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Capture rich diagnostic data (image quality, engine diffs) "
        "and write .diagnostics.json sidecar",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output structured JSON results to stdout (suppresses progress display)",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="scholardoc-ocr 0.1.0",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # Console setup
    no_color = args.no_color or os.environ.get("NO_COLOR") is not None
    console = Console(no_color=no_color)

    input_dir = Path(args.input_dir).expanduser().resolve()

    # Output directory
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = input_dir / "ocr_output"

    # Language resolution
    iso_codes = [c.strip() for c in args.language.split(",") if c.strip()]
    try:
        langs_tesseract, langs_surya = resolve_languages(iso_codes)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    # Environment validation
    from .environment import EnvironmentError as EnvError
    from .environment import log_startup_diagnostics, validate_environment

    try:
        validate_environment(langs_tesseract=langs_tesseract)
    except EnvError as e:
        console.print("[red]Environment check failed:[/red]")
        for problem in e.problems:
            console.print(f"  [red]\u2022[/red] {problem}")
        sys.exit(1)

    if args.verbose:
        log_startup_diagnostics(langs_tesseract=langs_tesseract)
        from .environment import check_gpu_availability

        gpu_available, gpu_message = check_gpu_availability()
        console.print(f"[dim]GPU: {gpu_message}[/dim]")

    # Find PDFs to process
    if args.files:
        pdf_files = []
        for filename in args.files:
            p = Path(filename)
            if p.is_absolute():
                resolved = p
            else:
                resolved = input_dir / filename
            if not resolved.exists():
                console.print(f"[yellow]Warning:[/yellow] File not found: {resolved}")
                continue
            if not resolved.name.lower().endswith(".pdf"):
                console.print(f"[yellow]Warning:[/yellow] Not a PDF file: {resolved}")
                continue
            pdf_files.append(str(resolved.relative_to(input_dir)))
        if not pdf_files:
            console.print("[red]No valid PDF files to process.[/red]")
            sys.exit(1)
    else:
        if args.recursive:
            pdf_files = [str(p.relative_to(input_dir)) for p in input_dir.rglob("*.pdf")]
        else:
            pdf_files = [str(p.relative_to(input_dir)) for p in input_dir.glob("*.pdf")]

        if not pdf_files:
            console.print(f"No PDF files found in {input_dir}")
            console.print("Use -f to specify files or -r to search recursively")
            sys.exit(1)

    config = PipelineConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        quality_threshold=args.quality,
        force_tesseract=args.force,
        force_surya=args.force_surya,
        strict_gpu=args.strict_gpu,
        debug=args.debug,
        max_samples=args.samples,
        max_workers=args.workers,
        files=pdf_files,
        langs_tesseract=langs_tesseract,
        langs_surya=langs_surya,
        keep_intermediates=args.keep_intermediates,
        timeout=args.timeout,
        extract_text=args.extract_text,
        diagnostics=args.diagnostics,
    )

    if args.json_output:
        from .callbacks import LoggingCallback

        callback = LoggingCallback()
    else:
        callback = RichCallback(console)

    try:
        batch = run_pipeline(config, callback=callback)
    except KeyboardInterrupt:
        if not args.json_output:
            console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)
    except Exception as e:
        if args.json_output:
            import json

            print(json.dumps({"error": str(e)}))
        elif args.debug:
            console.print_exception()
        else:
            console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    if args.json_output:
        print(batch.to_json(include_text=args.extract_text))
    else:
        _print_summary(console, batch, output_dir, args.quality, debug=args.debug)
    sys.exit(0 if batch.error_count == 0 else 1)


if __name__ == "__main__":
    main()
