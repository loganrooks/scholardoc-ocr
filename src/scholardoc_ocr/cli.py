"""Command-line interface."""

import argparse
import logging
import multiprocessing as mp
from pathlib import Path

from .pipeline import PipelineConfig, run_pipeline


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
            pdf_files = [p.name for p in input_dir.rglob("*.pdf")]
        else:
            pdf_files = [p.name for p in input_dir.glob("*.pdf")]

        if not pdf_files:
            print(f"No PDF files found in {input_dir}")
            print("Use -f to specify files or -r to search recursively")
            return

    print(f"Input:  {input_dir}")
    print(f"Output: {output_dir}")
    print(f"Found {len(pdf_files)} PDF(s) to process")
    print()

    config = PipelineConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        quality_threshold=args.quality,
        force_tesseract=args.force,
        debug=args.debug,
        max_samples=args.samples,
        max_workers=args.workers,
        files=pdf_files,
    )

    run_pipeline(config)


if __name__ == "__main__":
    main()
