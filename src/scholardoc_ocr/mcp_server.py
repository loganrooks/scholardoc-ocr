"""MCP server exposing the scholardoc-ocr pipeline as a tool for Claude Desktop."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from mcp.server.fastmcp import Context, FastMCP

_LOG_FILE = Path.home() / "scholardoc_mcp.log"


def _log(msg: str) -> None:
    """Append a line to the debug log file (bypasses logging framework)."""
    with open(_LOG_FILE, "a") as f:
        from datetime import datetime
        f.write(f"{datetime.now().isoformat()} {msg}\n")
        f.flush()


logger = logging.getLogger(__name__)

mcp = FastMCP("scholardoc-ocr")


# ---------------------------------------------------------------------------
# Async job infrastructure
# ---------------------------------------------------------------------------

_JOB_TTL_SECONDS = 3600  # 1 hour


@dataclass
class JobState:
    """Tracks an async OCR job."""

    job_id: str
    status: str = "running"  # running | completed | failed
    progress: dict = field(default_factory=dict)
    result: dict | None = None
    error: str | None = None
    created_at: float = field(default_factory=time.time)


_jobs: dict[str, JobState] = {}


def _cleanup_expired_jobs() -> None:
    """Remove completed/failed jobs older than TTL to prevent memory leaks."""
    now = time.time()
    expired = [
        jid
        for jid, job in _jobs.items()
        if job.status in ("completed", "failed")
        and (now - job.created_at) > _JOB_TTL_SECONDS
    ]
    for jid in expired:
        del _jobs[jid]


class _JobProgressCallback:
    """Callback that updates a JobState's progress dict."""

    def __init__(self, job: JobState) -> None:
        self._job = job

    def on_progress(self, event) -> None:
        self._job.progress = {
            "phase": event.phase,
            "current": event.current,
            "total": event.total,
            "filename": event.filename,
        }

    def on_phase(self, event) -> None:
        self._job.progress["phase"] = event.phase
        self._job.progress["phase_status"] = event.status

    def on_model(self, event) -> None:
        self._job.progress["model"] = event.model_name
        self._job.progress["model_status"] = event.status


async def _run_job(job: JobState, config) -> None:
    """Background task that runs the pipeline and updates job state."""
    try:
        from .pipeline import run_pipeline

        callback = _JobProgressCallback(job)
        batch = await asyncio.to_thread(run_pipeline, config, callback)
        job.status = "completed"
        job.result = batch.to_dict(include_text=False)
    except Exception as e:
        job.status = "failed"
        job.error = str(e)


@mcp.tool()
async def ocr_async(
    input_path: str,
    quality_threshold: float = 0.85,
    force_surya: bool = False,
    max_workers: int = 4,
    extract_text: bool = False,
) -> dict:
    """Start a long-running OCR job asynchronously.

    Returns a job_id immediately without blocking. Use ocr_status(job_id) to
    poll for progress and retrieve results when complete. Preferred for large
    files or batches that may take 10+ minutes.

    Args:
        input_path: Path to a PDF file or directory containing PDFs. Supports ~ expansion.
        quality_threshold: Quality score threshold (0-1) for Surya fallback. Default 0.85.
        force_surya: Force Surya OCR on all pages, skipping Tesseract.
        max_workers: Maximum parallel Tesseract workers.
        extract_text: If true, keep extracted .txt files alongside output PDFs.
    """
    from .pipeline import PipelineConfig

    _cleanup_expired_jobs()

    if not input_path or not input_path.strip():
        return {"error": f"input_path is empty or blank. Received: {input_path!r}"}

    resolved = Path(input_path).expanduser().resolve()
    if not resolved.exists():
        return {"error": f"Path does not exist: {resolved}"}

    if resolved.is_file():
        input_dir = resolved.parent
        output_dir = resolved.parent / "scholardoc_ocr"
        files = [resolved.name]
    else:
        input_dir = resolved
        output_dir = resolved / "scholardoc_ocr"
        files = []

    config = PipelineConfig(
        input_dir=input_dir,
        output_dir=output_dir,
        quality_threshold=quality_threshold,
        force_surya=force_surya,
        max_workers=max_workers,
        extract_text=extract_text,
    )
    if files:
        config.files = files

    job = JobState(job_id=str(uuid.uuid4()))
    _jobs[job.job_id] = job
    asyncio.create_task(_run_job(job, config))

    _log(f"ocr_async started job={job.job_id} input={resolved}")
    return {"job_id": job.job_id, "status": "running"}


@mcp.tool()
async def ocr_status(job_id: str) -> dict:
    """Check the status of an async OCR job.

    Args:
        job_id: The job ID returned by ocr_async().

    Returns a dict with job_id, status, progress, result (when complete),
    and error (if failed).
    """
    _cleanup_expired_jobs()

    job = _jobs.get(job_id)
    if job is None:
        return {"error": f"Unknown job: {job_id}"}

    return {
        "job_id": job.job_id,
        "status": job.status,
        "progress": job.progress,
        "result": job.result,
        "error": job.error,
    }


@mcp.tool()
async def ocr(
    input_path: str,
    ctx: Context,
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

    For long-running jobs (10+ minutes), prefer ocr_async() which returns immediately
    and lets you poll progress via ocr_status().

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

        await ctx.info(f"Starting OCR: {resolved}")

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
                    "error": (
                        f"Invalid page_range: '{page_range}'."
                        " Use 'start-end' (e.g. '45-80')"
                    )
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

        # Build config — set extract_text so pipeline preserves .txt files
        config = PipelineConfig(
            input_dir=input_dir if target_file is None else target_file.parent,
            output_dir=output_dir,
            quality_threshold=quality_threshold,
            force_surya=force_surya,
            max_workers=max_workers,
            extract_text=extract_text,
        )
        if target_file is not None:
            config.files = [target_file.name]

        # Run pipeline in thread to avoid blocking event loop.
        # NOTE: Fine-grained mid-pipeline progress is not available for the
        # synchronous tool because run_pipeline executes in a separate thread
        # and we cannot bridge async ctx.info calls from within it. Use
        # ocr_async() + ocr_status() for detailed progress on long jobs.
        result = await asyncio.to_thread(run_pipeline, config)
        result_dict = result.to_dict(include_text=False)
        file_summary = [
            (f.get('filename'), f.get('output_path'))
            for f in result_dict.get('files', [])
        ]
        _log(f"pipeline result keys per file: {file_summary}")
        for f in result_dict.get('files', []):
            if not f.get('success'):
                _log(
                    f"FAILED FILE: {f.get('filename')}"
                    f" - engine={f.get('engine')}"
                    f" error={f.get('error')!r}"
                )

        # Clean up temp page-range file
        if temp_page_file is not None and temp_page_file.exists():
            temp_page_file.unlink()

        # Use pipeline's post-processed .txt files instead of re-extracting
        # from the PDF (which would lose post-processing transforms like
        # dehyphenation and paragraph joining).
        if extract_text:
            for file_result in result_dict.get("files", []):
                out_path_str = file_result.get("output_path")
                if not out_path_str:
                    continue
                txt_path = Path(out_path_str).with_suffix(".txt")
                if txt_path.exists():
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

        success_count = sum(
            1 for f in result_dict.get("files", []) if f.get("success")
        )
        error_count = sum(
            1 for f in result_dict.get("files", []) if not f.get("success")
        )
        await ctx.info(f"OCR complete: {success_count} succeeded, {error_count} failed")

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
