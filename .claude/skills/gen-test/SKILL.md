---
name: gen-test
description: Generate pytest tests for scholardoc-ocr modules
disable-model-invocation: true
---

# Test Generation Skill

Generate pytest tests for the scholardoc-ocr project.

## Conventions

- Tests go in `tests/` at the project root
- Test files are named `test_<module>.py` matching `src/scholardoc_ocr/<module>.py`
- Use pytest fixtures, not unittest classes
- Mock external dependencies: ocrmypdf, marker, pymupdf
- Use `tmp_path` fixture for any file I/O
- Test quality thresholds with parametrize for edge cases

## Module-Specific Guidance

### quality.py tests
- Test `QualityAnalyzer` with known garbled text samples and known good text
- Test that whitelisted philosophical terms (German, French, Greek) are not flagged
- Parametrize across threshold values

### processor.py tests
- Mock `ocrmypdf.ocr()` and marker's processing functions
- Test `PDFProcessor` methods individually
- Use fixture PDFs or mock PyMuPDF document objects

### pipeline.py tests
- Mock `PDFProcessor` and `QualityAnalyzer` entirely
- Test the two-phase orchestration logic
- Test that Surya is only invoked for pages below threshold
- Test parallel execution with multiple files

### cli.py tests
- Use `click.testing.CliRunner` or `argparse` equivalent
- Test argument parsing and `PipelineConfig` construction
- Test default values match documented defaults
