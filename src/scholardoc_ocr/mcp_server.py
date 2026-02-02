"""MCP server exposing the scholardoc-ocr pipeline as a tool for Claude Desktop."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_LOG_FILE = Path.home() / "scholardoc_mcp.log"


def _log(msg: str) -> None:
    """Append a line to the debug log file (bypasses logging framework)."""
    with open(_LOG_FILE, "a") as f:
        from datetime import datetime
        f.write(f"{datetime.now().isoformat()} {msg}\n")
        f.flush()


logger = logging.getLogger(__name__)

mcp = FastMCP("scholardoc-ocr")


@mcp.tool()
async def ocr(
    input_path: str,
    quality_threshold: float = 0.85,
    force_surya: bool = False,
    max_workers: int = 4,
    extract_text: bool = False,
    page_range: str | None = None,
    output_name: str | None = None,
) -> dict:
    """Run OCR on a PDF file or directory of PDFs.

    Processes academic documents using a two-phase strategy: fast Tesseract OCR first,
    then Surya/Marker OCR on pages below the quality threshold. Returns structured
    metadata about the results (not the text content itself).

    Args:
        input_path: Path to a PDF file or directory containing PDFs. Supports ~ expansion.
        quality_threshold: Quality score threshold (0-1) for Surya fallback. Default 0.85.
        force_surya: Force Surya OCR on all pages, skipping Tesseract.
        max_workers: Maximum parallel Tesseract workers.
        extract_text: If true, extract text to a .txt file alongside each output PDF.
            The response includes the .txt path but not the text content.
        page_range: Page range to extract before OCR, e.g. "45-80" (1-based, inclusive).
            Only the specified pages will be processed.
        output_name: Rename the output PDF to this name. Only valid for single-file input.
    """
    resolved = None
    try:
        from .pipeline import PipelineConfig, run_pipeline

        _log(f"ocr called with input_path={input_path!r}")

        if not input_path or not input_path.strip():
            return {"error": f"input_path is empty or blank. Received: {input_path!r}"}

        resolved = Path(input_path).expanduser().resolve()
        _log(f"resolved={resolved} exists={resolved.exists()}")

        if not resolved.exists():
            return {"error": f"Path does not exist: {resolved}"}

        # Determine input/output directories
        temp_page_file = None
        if resolved.is_file():
            input_dir = resolved.parent
            output_dir = resolved.parent / "scholardoc_ocr"
            target_file = resolved
        else:
            input_dir = resolved
            output_dir = resolved / "scholardoc_ocr"
            target_file = None

        # Page range extraction
        if page_range is not None:
            if target_file is None:
                return {"error": "page_range is only supported for single-file input"}
            try:
                parts = page_range.split("-")
                if len(parts) != 2:
                    raise ValueError
                start, end = int(parts[0]), int(parts[1])
                if start < 1 or end < start:
                    raise ValueError
            except (ValueError, TypeError):
                return {
                    "error": f"Invalid page_range: '{page_range}'. Use 'start-end' (e.g. '45-80')"
                }

            import fitz

            doc = fitz.open(str(target_file))
            if end > len(doc):
                doc.close()
                return {"error": f"page_range end ({end}) exceeds document pages ({len(doc)})"}

            new_doc = fitz.open()
            new_doc.insert_pdf(doc, from_page=start - 1, to_page=end - 1)
            temp_name = f"{target_file.stem}_pages_{start}-{end}.pdf"
            temp_page_file = target_file.parent / temp_name
            new_doc.save(str(temp_page_file))
            new_doc.close()
            doc.close()

            target_file = temp_page_file

        # Build config
        config = PipelineConfig(
            input_dir=input_dir if target_file is None else target_file.parent,
            output_dir=output_dir,
            quality_threshold=quality_threshold,
            force_surya=force_surya,
            max_workers=max_workers,
        )
        if target_file is not None:
            config.files = [target_file.name]

        # Run pipeline in thread to avoid blocking event loop
        result = await asyncio.to_thread(run_pipeline, config)
        result_dict = result.to_dict(include_text=False)
        _log(f"pipeline result keys per file: {[(f.get('filename'), f.get('output_path')) for f in result_dict.get('files', [])]}")
        for f in result_dict.get('files', []):
            if not f.get('success'):
                _log(f"FAILED FILE: {f.get('filename')} - engine={f.get('engine')} error={f.get('error')}")

        # Clean up temp page-range file
        if temp_page_file is not None and temp_page_file.exists():
            temp_page_file.unlink()

        # Extract text post-processing
        if extract_text:
            import fitz

            for file_result in result_dict.get("files", []):
                out_path_str = file_result.get("output_path")
                if out_path_str:
                    out_path = Path(out_path_str)
                else:
                    continue
                if out_path.exists():
                    doc = fitz.open(str(out_path))
                    text_parts = [doc[i].get_text() for i in range(len(doc))]
                    doc.close()
                    txt_path = out_path.with_suffix(".txt")
                    txt_path.write_text("\n".join(text_parts), encoding="utf-8")
                    file_result["text_file"] = str(txt_path)

        # Output name post-processing
        if output_name is not None:
            files = result_dict.get("files", [])
            if len(files) != 1:
                return {"error": "output_name is only supported for single-file input"}
            out_path_str = files[0].get("output_path")
            if not out_path_str:
                return {"error": "output_name requires output_path in result"}
            out_path = Path(out_path_str)
            if out_path.exists():
                new_path = out_path.parent / output_name
                out_path.rename(new_path)
                files[0]["output_path"] = str(new_path)
                # Update text_file path if it exists
                if "text_file" in files[0]:
                    old_txt = Path(files[0]["text_file"])
                    if old_txt.exists():
                        new_txt = new_path.with_suffix(".txt")
                        old_txt.rename(new_txt)
                        files[0]["text_file"] = str(new_txt)

        return result_dict

    except Exception as e:
        import traceback
        _log(f"EXCEPTION: {e}\n{traceback.format_exc()}")
        return {"error": f"{e} (input_path was {input_path!r}, resolved to {resolved!r})"}


def main():
    """Entry point for the MCP server."""
    log_file = Path.home() / "scholardoc_mcp.log"
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(name)s %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(),
        ],
    )
    _log("MCP server starting")
    mcp.run()


if __name__ == "__main__":
    main()
