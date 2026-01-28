"""Progress callback protocol and event types for pipeline reporting."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class ProgressEvent:
    """Emitted during file/page processing."""

    phase: str
    current: int
    total: int
    filename: str | None = None
    worker_id: int | None = None
    eta_seconds: float | None = None


@dataclass
class PhaseEvent:
    """Emitted when a pipeline phase starts or completes."""

    phase: str
    status: str
    files_count: int = 0
    pages_count: int = 0


@dataclass
class ModelEvent:
    """Emitted during model loading lifecycle."""

    model_name: str
    status: str
    time_seconds: float | None = None


@runtime_checkable
class PipelineCallback(Protocol):
    """Protocol for receiving pipeline progress updates."""

    def on_progress(self, event: ProgressEvent) -> None: ...

    def on_phase(self, event: PhaseEvent) -> None: ...

    def on_model(self, event: ModelEvent) -> None: ...


class LoggingCallback:
    """Callback implementation that logs events via the logging module."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("scholardoc_ocr")

    def on_progress(self, event: ProgressEvent) -> None:
        self._logger.debug(
            "%s: %d/%d%s",
            event.phase,
            event.current,
            event.total,
            f" ({event.filename})" if event.filename else "",
        )

    def on_phase(self, event: PhaseEvent) -> None:
        self._logger.info(
            "Phase %s %s (files=%d, pages=%d)",
            event.phase,
            event.status,
            event.files_count,
            event.pages_count,
        )

    def on_model(self, event: ModelEvent) -> None:
        self._logger.info(
            "Model %s %s%s",
            event.model_name,
            event.status,
            f" ({event.time_seconds:.1f}s)" if event.time_seconds is not None else "",
        )


class NullCallback:
    """No-op callback used as default when no callback is provided."""

    def on_progress(self, event: ProgressEvent) -> None:
        pass

    def on_phase(self, event: PhaseEvent) -> None:
        pass

    def on_model(self, event: ModelEvent) -> None:
        pass
