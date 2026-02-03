"""Tests for multiprocess logging infrastructure."""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import time
from concurrent.futures import ProcessPoolExecutor
from logging.handlers import QueueHandler
from pathlib import Path

from scholardoc_ocr.logging_ import setup_main_logging, stop_logging, worker_log_initializer


def test_setup_main_logging_returns_queue_and_listener():
    """setup_main_logging returns a (Queue, QueueListener) pair."""
    log_queue, listener = setup_main_logging()
    try:
        assert isinstance(log_queue, mp.queues.Queue)
        from logging.handlers import QueueListener

        assert isinstance(listener, QueueListener)
    finally:
        stop_logging(listener)


def test_worker_log_initializer_adds_queue_handler():
    """worker_log_initializer adds a QueueHandler to the root logger."""
    log_queue = mp.Queue()
    worker_log_initializer(log_queue)

    root = logging.getLogger()
    queue_handlers = [h for h in root.handlers if isinstance(h, QueueHandler)]
    assert len(queue_handlers) >= 1

    # Clean up
    root.handlers.clear()


def _worker_emit_sentinel(sentinel: str) -> str:
    """Worker task: log a sentinel message (logging already configured via initializer)."""
    logging.getLogger("test.worker").info(sentinel)
    return "done"


def test_worker_logs_reach_main_process():
    """Log records from a worker process reach the main process via the queue."""
    import io

    log_queue, listener = setup_main_logging()

    # Add a StringIO handler to capture output in the listener
    captured = io.StringIO()
    string_handler = logging.StreamHandler(captured)
    string_handler.setFormatter(logging.Formatter("%(message)s"))
    listener.handlers = listener.handlers + (string_handler,)

    try:
        sentinel = f"SENTINEL_{time.monotonic_ns()}"
        with ProcessPoolExecutor(
            max_workers=1,
            initializer=worker_log_initializer,
            initargs=(log_queue,),
        ) as pool:
            future = pool.submit(_worker_emit_sentinel, sentinel)
            future.result(timeout=10)

        # Allow queue to drain
        time.sleep(1.0)

        output = captured.getvalue()
        assert sentinel in output, f"Expected '{sentinel}' in captured output: {output!r}"
    finally:
        stop_logging(listener)


def _worker_emit_file_msg(log_dir: str) -> int:
    """Worker task: log a message and return PID (logging configured via initializer)."""
    # Re-add file handler since initializer doesn't know log_dir at pool creation
    # We test via a separate approach: use initializer with log_dir
    logging.getLogger("test.file").info("file-test-message")
    return os.getpid()


def _worker_file_initializer(log_queue: mp.Queue, log_dir: str) -> None:
    """Initializer that sets up both queue and file logging."""
    worker_log_initializer(log_queue, log_dir=Path(log_dir))


def test_per_worker_log_file_created(tmp_path: Path):
    """worker_log_initializer creates a worker_{pid}.log file in log_dir."""
    log_queue, listener = setup_main_logging()
    try:
        with ProcessPoolExecutor(
            max_workers=1,
            initializer=_worker_file_initializer,
            initargs=(log_queue, str(tmp_path)),
        ) as pool:
            future = pool.submit(_worker_emit_file_msg, str(tmp_path))
            worker_pid = future.result(timeout=10)

        log_file = tmp_path / f"worker_{worker_pid}.log"
        assert log_file.exists(), (
            f"Expected {log_file} to exist, found: {list(tmp_path.iterdir())}"
        )
        contents = log_file.read_text()
        assert "file-test-message" in contents
    finally:
        stop_logging(listener)


def test_stop_logging_idempotent():
    """stop_logging can be called multiple times without error."""
    _, listener = setup_main_logging()
    stop_logging(listener)
    stop_logging(listener)  # Should not raise
