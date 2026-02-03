"""Multiprocess logging infrastructure for the OCR pipeline.

On macOS, Python's default process start method is "spawn" (as of 3.8+), and even
when "fork" is used, the combination of fork + logging is broken: file handlers in
child processes can deadlock or write interleaved output because the logging lock
state is copied but the lock itself is invalid in the child.

The solution is QueueHandler/QueueListener from the stdlib. Worker processes send
all log records through a multiprocessing.Queue to the main process, where a
QueueListener dispatches them to the real handlers (console, file). This avoids
any handler I/O in worker processes and guarantees correct, serialized output.

Public API:
    setup_main_logging  — call once in main process before spawning workers
    worker_log_initializer — pass as initializer= to ProcessPoolExecutor
    stop_logging        — call in a finally block after workers finish
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from pathlib import Path

__all__ = ["setup_main_logging", "worker_log_initializer", "stop_logging"]

_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def setup_main_logging(
    log_dir: Path | None = None,
    verbose: bool = False,
) -> tuple[mp.Queue, QueueListener]:
    """Set up main-process logging with a QueueListener.

    Creates a multiprocessing.Queue and a QueueListener that dispatches to a
    console StreamHandler (and optionally a RotatingFileHandler if *log_dir*
    is provided).

    Args:
        log_dir: If given, a ``pipeline.log`` file is written here.
        verbose: If True, root logger level is DEBUG; otherwise INFO.

    Returns:
        (queue, listener) — pass *queue* to workers, call ``stop_logging(listener)``
        when done.
    """
    log_queue: mp.Queue = mp.Queue()

    formatter = logging.Formatter(_LOG_FORMAT)

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(formatter)

    handlers: list[logging.Handler] = [console]

    # Optional file handler
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "pipeline.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
        )
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    listener = QueueListener(log_queue, *handlers, respect_handler_level=True)
    listener.start()

    # Configure root logger level
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)

    return log_queue, listener


def worker_log_initializer(
    log_queue: mp.Queue,
    log_dir: Path | None = None,
) -> None:
    """Initializer for ProcessPoolExecutor workers.

    Replaces all root logger handlers with a QueueHandler that sends records
    to the main process. Optionally adds a per-worker FileHandler.

    Args:
        log_queue: The queue returned by :func:`setup_main_logging`.
        log_dir: If given, a ``worker_{pid}.log`` file is written here.
    """
    root = logging.getLogger()
    # Clear any inherited handlers
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    # QueueHandler sends records to main process
    root.addHandler(QueueHandler(log_queue))

    # Optional per-worker file
    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        formatter = logging.Formatter(_LOG_FORMAT)
        fh = logging.FileHandler(log_dir / f"worker_{os.getpid()}.log")
        fh.setFormatter(formatter)
        root.addHandler(fh)


def stop_logging(listener: QueueListener) -> None:
    """Stop the QueueListener safely.

    Safe to call multiple times — silently ignores errors if already stopped.
    """
    try:
        listener.stop()
    except Exception:  # noqa: BLE001
        pass
