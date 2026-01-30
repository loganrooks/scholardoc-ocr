"""Command-line interface."""

import argparse
import logging
import multiprocessing as mp
import sys
from pathlib import Path

from .pipeline import PipelineConfig, run_pipeline
from .types import BatchResult, OCREngine


def _print_summary(batch: BatchResult, output_dir: Path, debug: bool = False) -> None:
    """Print a formatted summary of the batch result."""
    print()
    print("=" * 60)
    print("OCR Pipeline Summary")
    print("=" * 60)
    print(f"  Total files:  {len(batch.files)}")
    print(f"  Successful:   {batch.success_count}")
    print(f"  Errors:       {batch.error_count}")
    print(f"  Total time:   {batch.total_time_seconds:.1f}s")
    print()

    # Files with Surya enhancement
    surya_files = [
        f for f in batch.files
        if any(p.engine == OCREngine.SURYA for p in f.pages)
    ]
    if surya_files:
        print(f"  Surya-enhanced files: {len(surya_files)}")
        for sf in surya_files:
            surya_pages = [p for p in sf.pages if p.engine == OCREngine.SURYA]
            print(f"    - {sf.filename} ({len(surya_pages)} pages)")
        print()

    # Per-file summary
    print("Files:")
    print(f"  {'Filename':<40} {'Pages':>5} {'Quality':>8} {'Engine':<10} {'Time':>6}")
    print(f"  {'-'*40} {'-'*5} {'-'*8} {'-'*10} {'-'*6}")
    for f in batch.files:
        if f.success:
            print(
                f"  {f.filename:<40} {f.page_count:>5} "
                f"{f.quality_score:>7.1%} {str(f.engine):<10} {f.time_seconds:>5.1f}s"
            )
        else:
            print(f"  {f.filename:<40} {'ERROR':<5}  {f.error or 'Unknown error'}")

    # Debug: per-page breakdown for flagged files
    if debug:
        flagged_files = [f for f in batch.files if f.flagged_pages]
        if flagged_files:
            print()
            print("Flagged Page Details:")
            for f in flagged_files:
                print(f"  {f.filename}:")
                for p in f.pages:
                    if p.flagged or p.engine == OCREngine.SURYA:
                        print(
                            f"    Page {p.page_number:>3}: "
                            f"quality={p.quality_score:.1%}  engine={p.engine}"
                        )

    print()
    print(f"  Output: {output_dir / 'final'}")
    print()


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
        """,
    )

    parser.add_argument(
        "input_dir",
        nargs="?",
        default=".",
        help="Input directory containing PDFs (default: current directory)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output directory (default: <input_dir>/ocr_output)",
    )
    parser.add_argument(
        "-q", "--quality",
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
        "--debug",
        action="store_true",
        help="Show detailed quality analysis with sample problem text.",
    )
    parser.add_argument(
        "-s", "--samples",
        type=int,
        default=20,
        help="Number of problem samples to show in debug mode (default: 20)",
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=mp.cpu_count(),
        help=f"Parallel workers (default: {mp.cpu_count()})",
    )
    parser.add_argument(
        "-f", "--files",
        nargs="+",
        help="Specific PDF files to process (instead of all PDFs in input_dir)",
    )
    parser.add_argument(
        "-r", "--recursive",
        action="store_true",
        help="Recursively search subdirectories for PDFs",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    input_dir = Path(args.input_dir).expanduser().resolve()

    # Default output to <input_dir>/ocr_output
    if args.output:
        output_dir = Path(args.output).expanduser().resolve()
    else:
        output_dir = input_dir / "ocr_output"

    # Find PDFs to process
    if args.files:
        # Specific files provided
        pdf_files = [f for f in args.files if f.lower().endswith('.pdf')]
    else:
        # Auto-discover PDFs in input directory
        if args.recursive:
            pdf_files = [str(p.relative_to(input_dir)) for p in input_dir.rglob("*.pdf")]
        else:
            pdf_files = [str(p.relative_to(input_dir)) for p in input_dir.glob("*.pdf")]

        if not pdf_files:
            print(f"No PDF files found in {input_dir}")
            print("Use -f to specify files or -r to search recursively")
            sys.exit(1)

    config = PipelineConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        quality_threshold=args.quality,
        force_tesseract=args.force,
        force_surya=args.force_surya,
        debug=args.debug,
        max_samples=args.samples,
        max_workers=args.workers,
        files=pdf_files,
    )

    batch = run_pipeline(config)
    _print_summary(batch, output_dir, debug=args.debug)
    sys.exit(0 if batch.error_count == 0 else 1)


if __name__ == "__main__":
    main()
