#!/usr/bin/env python3
"""Analyze baseline diagnostics to build coverage matrix for page selection.

Reads all .diagnostics.json files referenced in the corpus manifest and produces:
1. A human-readable coverage report (printed to stdout)
2. A machine-readable page_selection.json with recommended pages

The coverage matrix identifies struggle categories, gray zone pages, and signal
disagreement pages from Phase 15 diagnostic output. It recommends two sets of
pages for ground truth creation:

- **Difficult pages:** Coverage-based selection ensuring representation of each
  struggle category, plus all gray zone and signal disagreement pages.
- **Regression pages:** Clean pages that should always pass quality threshold,
  including ToC, front matter, body text, and bibliography pages.

Usage:
    python scripts/corpus/build_coverage_matrix.py
    python scripts/corpus/build_coverage_matrix.py --corpus-dir tests/corpus

Page numbers are 0-indexed throughout, matching PageResult.page_number convention.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_manifest(corpus_dir: Path) -> dict:
    """Load and return the corpus manifest."""
    manifest_path = corpus_dir / "corpus.json"
    if not manifest_path.exists():
        print(f"Error: manifest not found at {manifest_path}")
        return {"documents": []}
    with open(manifest_path) as f:
        return json.load(f)


def build_coverage_matrix(
    corpus_dir: Path,
) -> tuple[
    dict[str, list[tuple[str, int]]],
    list[tuple[str, int]],
    list[tuple[str, int]],
    dict[str, list[dict]],
]:
    """Parse diagnostic sidecars and build coverage matrix.

    Returns:
        Tuple of (struggle_categories, gray_zone_pages, disagreement_pages, all_pages)
        where all_pages maps doc_id -> list of page dicts from diagnostics.
    """
    manifest = load_manifest(corpus_dir)

    struggle_categories: dict[str, list[tuple[str, int]]] = defaultdict(list)
    gray_zone_pages: list[tuple[str, int]] = []
    disagreement_pages: list[tuple[str, int]] = []
    all_pages: dict[str, list[dict]] = {}
    baselines_found = 0

    for doc in manifest["documents"]:
        doc_id = doc["id"]
        baseline_path = corpus_dir / doc["baseline"]["path"]
        diag_file = baseline_path / doc["baseline"]["diagnostics_file"]

        if not diag_file.exists():
            print(f"WARNING: No baseline for {doc_id} (expected: {diag_file})")
            continue

        baselines_found += 1

        with open(diag_file) as f:
            data = json.load(f)

        doc_pages = data.get("pages", [])
        all_pages[doc_id] = doc_pages

        for page in doc_pages:
            diag = page.get("diagnostics", {})
            page_num = page["page_number"]

            for cat in diag.get("struggle_categories", []):
                struggle_categories[cat].append((doc_id, page_num))

            if "gray_zone" in diag.get("struggle_categories", []):
                gray_zone_pages.append((doc_id, page_num))

            if diag.get("has_signal_disagreement"):
                disagreement_pages.append((doc_id, page_num))

    if baselines_found == 0:
        print("\nNo baselines found. Run the pipeline with --diagnostics first:")
        print("  ocr --diagnostics --extract-text --force <pdf> -o <baseline-dir>")
        print("\nSee 16-CONTEXT.md for baseline capture instructions.")

    return dict(struggle_categories), gray_zone_pages, disagreement_pages, all_pages


def select_difficult_pages(
    struggle_categories: dict[str, list[tuple[str, int]]],
    gray_zone_pages: list[tuple[str, int]],
    disagreement_pages: list[tuple[str, int]],
) -> dict[str, list[int]]:
    """Select difficult pages for ground truth based on coverage.

    Strategy:
    - At least 2-3 pages per struggle category (preferring cross-document diversity)
    - All gray zone pages (most informative for threshold calibration)
    - All signal disagreement pages (reveal quality model inconsistencies)
    """
    selected: set[tuple[str, int]] = set()

    for _cat, pages in struggle_categories.items():
        # Prefer diversity: try to pick from different documents
        by_doc: dict[str, list[int]] = defaultdict(list)
        for doc_id, page_num in pages:
            by_doc[doc_id].append(page_num)

        added = 0
        # First pass: one from each document
        for doc_id, doc_pages in sorted(by_doc.items()):
            if added >= 3:
                break
            selected.add((doc_id, doc_pages[0]))
            added += 1

        # Second pass: fill to minimum 2 if needed
        if added < 2:
            for doc_id, page_num in pages[:2]:
                selected.add((doc_id, page_num))

    # Add all gray zone and signal disagreement pages
    selected.update(gray_zone_pages)
    selected.update(disagreement_pages)

    # Group by document
    result: dict[str, list[int]] = defaultdict(list)
    for doc_id, page_num in sorted(selected):
        result[doc_id].append(page_num)

    return dict(result)


def select_regression_pages(
    all_pages: dict[str, list[dict]],
) -> dict[str, list[int]]:
    """Select regression pages: clean pages that should always pass.

    Strategy per document:
    - 1 ToC/index page (typically early pages with quality > 0.90)
    - 1 front matter page (page 0-2)
    - 2-3 clean body text pages (quality > 0.90, no struggle categories)
    - 1 bibliography page if present (typically near end)
    """
    result: dict[str, list[int]] = {}

    for doc_id, pages in all_pages.items():
        if not pages:
            continue

        selected: list[int] = []
        total_pages = len(pages)

        # Front matter: pick page 0 or 1
        for p in pages[:3]:
            diag = p.get("diagnostics", {})
            cats = diag.get("struggle_categories", [])
            if not cats:
                selected.append(p["page_number"])
                break

        # ToC page: typically pages 3-10, look for clean pages
        for p in pages[3:min(10, total_pages)]:
            diag = p.get("diagnostics", {})
            quality = p.get("quality_score", 0)
            cats = diag.get("struggle_categories", [])
            if quality > 0.90 and not cats and p["page_number"] not in selected:
                selected.append(p["page_number"])
                break

        # Clean body text: pages in the middle third, quality > 0.90, no struggles
        body_start = total_pages // 4
        body_end = 3 * total_pages // 4
        body_clean = []
        for p in pages[body_start:body_end]:
            diag = p.get("diagnostics", {})
            quality = p.get("quality_score", 0)
            cats = diag.get("struggle_categories", [])
            if quality > 0.90 and not cats and p["page_number"] not in selected:
                body_clean.append(p["page_number"])

        # Take 2-3 evenly spaced clean body pages
        if body_clean:
            step = max(1, len(body_clean) // 3)
            for i in range(0, len(body_clean), step):
                if len([s for s in selected if body_start <= s <= body_end]) >= 3:
                    break
                selected.append(body_clean[i])

        # Bibliography: near the end, look for clean page
        for p in reversed(pages[-20:]):
            diag = p.get("diagnostics", {})
            quality = p.get("quality_score", 0)
            cats = diag.get("struggle_categories", [])
            if quality > 0.90 and not cats and p["page_number"] not in selected:
                selected.append(p["page_number"])
                break

        result[doc_id] = sorted(selected)

    return result


def print_report(
    struggle_categories: dict[str, list[tuple[str, int]]],
    gray_zone_pages: list[tuple[str, int]],
    disagreement_pages: list[tuple[str, int]],
    difficult: dict[str, list[int]],
    regression: dict[str, list[int]],
) -> None:
    """Print human-readable coverage report."""
    print("=" * 60)
    print("COVERAGE MATRIX REPORT")
    print("=" * 60)

    if not struggle_categories:
        print("\nNo struggle categories found in diagnostic data.")
        print("This may mean no baselines have been captured yet.")
        return

    print("\n--- Struggle Categories ---\n")
    for cat, pages in sorted(
        struggle_categories.items(), key=lambda x: -len(x[1])
    ):
        print(f"  {cat}: {len(pages)} pages")
        for doc_id, page_num in pages[:5]:
            print(f"    - {doc_id} page {page_num}")
        if len(pages) > 5:
            print(f"    ... and {len(pages) - 5} more")

    print("\n--- Special Pages ---\n")
    print(f"  Gray zone pages: {len(gray_zone_pages)}")
    for doc_id, page_num in gray_zone_pages[:10]:
        print(f"    - {doc_id} page {page_num}")
    if len(gray_zone_pages) > 10:
        print(f"    ... and {len(gray_zone_pages) - 10} more")

    print(f"  Signal disagreement pages: {len(disagreement_pages)}")
    for doc_id, page_num in disagreement_pages[:10]:
        print(f"    - {doc_id} page {page_num}")
    if len(disagreement_pages) > 10:
        print(f"    ... and {len(disagreement_pages) - 10} more")

    print("\n--- Recommended Selection ---\n")

    total_difficult = sum(len(pages) for pages in difficult.values())
    print(f"  DIFFICULT pages: {total_difficult}")
    for doc_id, pages in sorted(difficult.items()):
        print(f"    {doc_id}: {len(pages)} pages - {pages}")

    total_regression = sum(len(pages) for pages in regression.values())
    print(f"\n  REGRESSION pages: {total_regression}")
    for doc_id, pages in sorted(regression.items()):
        print(f"    {doc_id}: {len(pages)} pages - {pages}")

    total = total_difficult + total_regression
    print(f"\n  TOTAL recommended: {total} pages")
    print("=" * 60)


def write_selection_json(
    corpus_dir: Path,
    struggle_categories: dict[str, list[tuple[str, int]]],
    difficult: dict[str, list[int]],
    regression: dict[str, list[int]],
) -> None:
    """Write machine-readable page selection JSON."""
    coverage_summary = {cat: len(pages) for cat, pages in struggle_categories.items()}
    total_pages = sum(len(p) for p in difficult.values()) + sum(
        len(p) for p in regression.values()
    )

    selection = {
        "difficult": difficult,
        "regression": regression,
        "total_pages": total_pages,
        "coverage_summary": coverage_summary,
    }

    out_path = corpus_dir / "page_selection.json"
    with open(out_path, "w") as f:
        json.dump(selection, f, indent=2)
    print(f"\nPage selection written to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build coverage matrix from diagnostic baselines.",
        epilog="Run after capturing baselines with: ocr --diagnostics --extract-text",
    )
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=Path("tests/corpus"),
        help="Path to corpus directory (default: tests/corpus)",
    )

    args = parser.parse_args()

    # Build coverage matrix from diagnostic data
    struggle_categories, gray_zone_pages, disagreement_pages, all_pages = (
        build_coverage_matrix(args.corpus_dir)
    )

    # Select pages
    difficult = select_difficult_pages(
        struggle_categories, gray_zone_pages, disagreement_pages
    )
    regression = select_regression_pages(all_pages)

    # Print report
    print_report(
        struggle_categories,
        gray_zone_pages,
        disagreement_pages,
        difficult,
        regression,
    )

    # Write machine-readable selection (only if we have data)
    if struggle_categories or all_pages:
        write_selection_json(args.corpus_dir, struggle_categories, difficult, regression)


if __name__ == "__main__":
    main()
