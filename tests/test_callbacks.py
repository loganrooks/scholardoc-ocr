"""Tests for callback protocol wiring into pipeline and processor."""

from __future__ import annotations

import inspect
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from scholardoc_ocr.callbacks import (
    LoggingCallback,
    ModelEvent,
    NullCallback,
    PhaseEvent,
    PipelineCallback,
    ProgressEvent,
)
from scholardoc_ocr.pipeline import ExtendedResult, PipelineConfig, run_pipeline
from scholardoc_ocr.processor import PDFProcessor


class CollectorCallback:
    """Test callback that collects all events."""

    def __init__(self):
        self.phase_events: list[PhaseEvent] = []
        self.progress_events: list[ProgressEvent] = []
        self.model_events: list[ModelEvent] = []

    def on_phase(self, event: PhaseEvent) -> None:
        self.phase_events.append(event)

    def on_progress(self, event: ProgressEvent) -> None:
        self.progress_events.append(event)

    def on_model(self, event: ModelEvent) -> None:
        self.model_events.append(event)


class TestProtocolCompliance:
    def test_logging_callback_satisfies_protocol(self):
        assert isinstance(LoggingCallback(), PipelineCallback)

    def test_null_callback_satisfies_protocol(self):
        assert isinstance(NullCallback(), PipelineCallback)

    def test_collector_callback_satisfies_protocol(self):
        assert isinstance(CollectorCallback(), PipelineCallback)


class TestCallbackWiring:
    def test_run_pipeline_accepts_callback(self):
        sig = inspect.signature(run_pipeline)
        assert "callback" in sig.parameters

    def test_no_events_when_no_files(self, tmp_path):
        """No files means early return, no events emitted."""
        config = PipelineConfig(
            input_dir=tmp_path,
            output_dir=tmp_path / "output",
            files=[],
        )
        collector = CollectorCallback()
        results = run_pipeline(config, callback=collector)
        assert results == []
        assert len(collector.phase_events) == 0

    def test_default_callback_is_logging(self, tmp_path):
        config = PipelineConfig(
            input_dir=tmp_path,
            output_dir=tmp_path / "output",
            files=[],
        )
        with patch("scholardoc_ocr.pipeline.LoggingCallback") as mock_cls:
            mock_cls.return_value = NullCallback()
            run_pipeline(config)
            mock_cls.assert_called_once()

    def test_processor_callback_signature(self):
        sig = inspect.signature(PDFProcessor.run_surya_batch)
        assert "callback" in sig.parameters
        assert "progress_callback" not in sig.parameters


class TestCallbackEventsFire:
    def test_phase_events_fire_during_processing(self, tmp_path):
        """Mock _process_single to test pipeline callback emissions."""
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"

        # Create a dummy file so path.exists() passes
        dummy = input_dir / "test.pdf"
        dummy.write_bytes(b"%PDF-1.4 dummy")

        config = PipelineConfig(
            input_dir=input_dir,
            output_dir=output_dir,
            files=["test.pdf"],
            max_workers=1,
        )

        fake_result = ExtendedResult(
            filename="test.pdf",
            success=True,
            method="tesseract",
            quality_score=0.95,
            output_text=output_dir / "final" / "test.txt",
            output_pdf=output_dir / "final" / "test.pdf",
            time_seconds=1.0,
            page_count=5,
            file_size_mb=1.0,
        )

        collector = CollectorCallback()

        # Mock get_page_count, _process_single, and use ThreadPoolExecutor to avoid pickling
        with (
            patch("scholardoc_ocr.pipeline.PDFProcessor") as mock_proc_cls,
            patch("scholardoc_ocr.pipeline._process_single", return_value=fake_result),
            patch("scholardoc_ocr.pipeline.ProcessPoolExecutor", ThreadPoolExecutor),
        ):
            mock_proc = MagicMock()
            mock_proc.get_page_count.return_value = 5
            mock_proc_cls.return_value = mock_proc

            results = run_pipeline(config, callback=collector)

        assert len(results) == 1

        # Should have Phase 1 started + completed = 2 PhaseEvents minimum
        phase_names = [(e.phase, e.status) for e in collector.phase_events]
        assert ("tesseract", "started") in phase_names
        assert ("tesseract", "completed") in phase_names

        # Should have 1 ProgressEvent (one file)
        assert len(collector.progress_events) >= 1
        assert collector.progress_events[0].phase == "tesseract"
        assert collector.progress_events[0].filename == "test.pdf"
