#!/usr/bin/env python3
"""Render selected PDF pages as 300 DPI PNGs for Opus vision transcription.

Reads the corpus manifest (tests/corpus/corpus.json) to locate PDF symlinks,
then renders specified pages at publication quality for ground truth creation.

Usage:
    python scripts/corpus/render_pages.py <document-id> <page_numbers...>
    python scripts/corpus/render_pages.py <document-id> --all-selected

Examples:
    python scripts/corpus/render_pages.py derrida-grammatology 42 73 150 201
    python scripts/corpus/render_pages.py simondon-technical-objects --all-selected

Page numbers are 0-indexed, matching PageResult.page_number convention.
"""

import argparse
import json
import sys
from pathlib import Path


def load_manifest(corpus_dir: Path) -> dict:
    """Load and return the corpus manifest."""
    manifest_path = corpus_dir / "corpus.json"
    if not manifest_path.exists():
        print(f"Error: manifest not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)
    with open(manifest_path) as f:
        return json.load(f)


def find_document(manifest: dict, doc_id: str) -> dict:
    """Find a document entry in the manifest by ID."""
    for doc in manifest["documents"]:
        if doc["id"] == doc_id:
            return doc
    print(f"Error: document '{doc_id}' not found in manifest", file=sys.stderr)
    print(
        f"Available documents: {[d['id'] for d in manifest['documents']]}",
        file=sys.stderr,
    )
    sys.exit(1)


def get_selected_pages(doc_entry: dict) -> list[int]:
    """Get page numbers from ground_truth_pages in the manifest."""
    gt_pages = doc_entry.get("ground_truth_pages", {})
    if not gt_pages:
        print(
            f"Warning: no ground_truth_pages defined for '{doc_entry['id']}'",
            file=sys.stderr,
        )
        return []
    return sorted(int(p) for p in gt_pages.keys())


def render_pages(
    corpus_dir: Path, doc_id: str, page_numbers: list[int]
) -> list[Path]:
    """Render specific pages from a PDF as 300 DPI PNGs.

    Args:
        corpus_dir: Path to tests/corpus/ directory.
        doc_id: Document identifier from the manifest.
        page_numbers: 0-indexed page numbers to render.

    Returns:
        List of paths to rendered PNG files.
    """
    try:
        import fitz
    except ImportError:
        print(
            "Error: PyMuPDF (fitz) is required. Install with: pip install pymupdf",
            file=sys.stderr,
        )
        sys.exit(1)

    manifest = load_manifest(corpus_dir)
    doc_entry = find_document(manifest, doc_id)
    pdf_path = corpus_dir / doc_entry["pdf_symlink"]

    if not pdf_path.exists():
        print(f"Error: PDF not found at {pdf_path}", file=sys.stderr)
        print(
            f"Create a symlink: ln -s /path/to/actual.pdf {pdf_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    output_dir = corpus_dir / "images" / doc_id
    output_dir.mkdir(parents=True, exist_ok=True)

    rendered: list[Path] = []
    doc = fitz.open(pdf_path)
    try:
        total_pages = len(doc)
        for page_num in page_numbers:
            if page_num < 0 or page_num >= total_pages:
                print(
                    f"Warning: page {page_num} out of range "
                    f"(valid: 0-{total_pages - 1}), skipping",
                    file=sys.stderr,
                )
                continue
            page = doc[page_num]
            pix = page.get_pixmap(dpi=300)
            out_path = output_dir / f"page_{page_num:03d}.png"
            pix.save(str(out_path))
            print(f"Rendered page {page_num} -> {out_path}")
            rendered.append(out_path)
    finally:
        doc.close()

    if rendered:
        print(f"\nRendered {len(rendered)} page(s) to {output_dir}")
    else:
        print("No pages were rendered.")

    return rendered


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render PDF pages as 300 DPI PNGs for Opus transcription.",
        epilog="Page numbers are 0-indexed (matching PageResult convention).",
    )
    parser.add_argument("document_id", help="Document ID from corpus.json manifest")
    parser.add_argument(
        "pages",
        nargs="*",
        type=int,
        help="0-indexed page numbers to render",
    )
    parser.add_argument(
        "--all-selected",
        action="store_true",
        help="Render all pages listed in ground_truth_pages from manifest",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("tests/corpus"),
        help="Path to corpus directory (default: tests/corpus)",
    )

    args = parser.parse_args()

    if args.all_selected:
        manifest = load_manifest(args.corpus_dir)
        doc_entry = find_document(manifest, args.document_id)
        page_numbers = get_selected_pages(doc_entry)
        if not page_numbers:
            print("No pages to render (ground_truth_pages is empty).")
            sys.exit(0)
    elif args.pages:
        page_numbers = args.pages
    else:
        parser.error("Provide page numbers or use --all-selected")

    render_pages(args.corpus_dir, args.document_id, page_numbers)


if __name__ == "__main__":
    main()
