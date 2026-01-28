# Testing Patterns

**Analysis Date:** 2026-01-28

## Test Framework

**Runner:**
- pytest (version >=8.0.0)
- Config: Not explicitly defined in `pyproject.toml`; uses pytest defaults
- No custom pytest configuration found (no `pytest.ini`, `setup.cfg`, or `[tool.pytest.ini_options]`)

**Assertion Library:**
- Standard Python `assert` statements (pytest native)
- No third-party assertion libraries

**Run Commands:**
```bash
pytest                          # Run all tests (no tests exist currently)
pytest -v                       # Verbose output
pytest --cov                    # Coverage report (no coverage config found)
```

## Test File Organization

**Current Status:**
- **No test files currently exist** in the repository
- Tests directory: `tests/` does not exist
- Test suite is empty

**Expected Organization (when implemented):**
- **Location:** Tests should be co-located in `tests/` directory at repository root
- **Naming:** Follow pytest convention: `test_*.py` or `*_test.py`
- **Suggested structure:**
  ```
  tests/
  ├── test_cli.py           # Tests for CLI argument parsing (cli.py)
  ├── test_pipeline.py      # Tests for orchestration (pipeline.py)
  ├── test_processor.py     # Tests for PDF operations (processor.py)
  ├── test_quality.py       # Tests for quality analysis (quality.py)
  └── fixtures/             # Test data and fixtures
      ├── sample_pdfs/      # Small test PDFs
      └── expected_outputs/ # Known good outputs
  ```

## Test Structure

**Recommended Suite Organization:**
When tests are implemented, follow this pattern based on pytest conventions:

```python
import pytest
from pathlib import Path
from scholardoc_ocr.quality import QualityAnalyzer, QualityResult

class TestQualityAnalyzer:
    """Test suite for QualityAnalyzer class."""

    def setup_method(self):
        """Called before each test method."""
        self.analyzer = QualityAnalyzer(threshold=0.85)

    def teardown_method(self):
        """Called after each test method."""
        # Cleanup if needed
        pass

    def test_analyze_valid_english_text(self):
        """Test analysis of clean English text."""
        text = "This is a valid English sentence with proper words."
        result = self.analyzer.analyze(text)

        assert result.score >= 0.9
        assert result.flagged is False
        assert result.garbled_count < 2
```

**Patterns:**
- Use class-based test organization: `class TestClassName:`
- Use `setup_method()` and `teardown_method()` for fixtures per test
- Use `@pytest.fixture` for shared test data
- One logical test per method; method names start with `test_`
- Use descriptive test names: `test_analyze_valid_english_text()` not `test_analyze()`

## Mocking

**Framework:** Python `unittest.mock` (standard library)

**Recommended Mocking Patterns:**

```python
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

class TestPDFProcessor:
    """Test suite for PDFProcessor."""

    @patch('scholardoc_ocr.processor.fitz')
    def test_extract_text_with_mock_fitz(self, mock_fitz):
        """Test text extraction with mocked PyMuPDF."""
        mock_doc = MagicMock()
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Sample text"
        mock_doc.__iter__ = lambda self: iter([mock_page])
        mock_fitz.open.return_value = mock_doc

        processor = PDFProcessor()
        result = processor.extract_text(Path("test.pdf"))

        assert "Sample text" in result
```

**What to Mock:**
- External subprocess calls: `subprocess.run()` (ocrmypdf, Tesseract)
- Heavy library imports: `fitz` (PyMuPDF), `marker` (Surya models)
- File I/O: Use temporary directories (`tmp_path` fixture)
- Network/API calls: (Not present in current codebase)

**What NOT to Mock:**
- Core logic of methods being tested
- Simple utility functions without side effects
- Dataclass initialization
- Regex pattern matching in `QualityAnalyzer` (test behavior, not implementation)

## Fixtures and Factories

**Test Data (when created):**
Should follow this pattern in a `tests/conftest.py`:

```python
import pytest
from pathlib import Path
from scholardoc_ocr.quality import QualityResult, QualityAnalyzer

@pytest.fixture
def sample_text_valid():
    """Clean, valid English text for testing."""
    return (
        "Levinas argues that ethics precedes ontology. The Other approaches us "
        "through the face, which commands us not to kill. This responsibility "
        "is infinite and asymmetrical."
    )

@pytest.fixture
def sample_text_garbled():
    """Text with OCR errors and garbling."""
    return (
        "Lev1nas argues thæt ethx precedes ont01ogy. The 0ther approaches us "
        "thru teh face, wich comands us nt0 k1ll. Thys respnbylty "
        "is infnite annd asymm3trical."
    )

@pytest.fixture
def quality_analyzer():
    """QualityAnalyzer instance with default settings."""
    return QualityAnalyzer(threshold=0.85, max_samples=10)

@pytest.fixture
def tmp_pdf_file(tmp_path):
    """Create a minimal test PDF file."""
    # Requires pymupdf to create a test PDF
    import fitz
    doc = fitz.open()
    doc.new_page()
    output_path = tmp_path / "test.pdf"
    doc.save(output_path)
    doc.close()
    return output_path
```

**Location:**
- Centralized in `tests/conftest.py` for shared fixtures
- Test-specific data in `tests/fixtures/` directory
- Temporary files created with pytest's `tmp_path` fixture

## Coverage

**Requirements:** Not enforced; no coverage configuration in `pyproject.toml`

**Recommended Coverage Goals:**
- Core logic (quality analysis, processor methods): 80%+
- CLI argument parsing: 70%+
- Integration points (pipeline orchestration): 60%+ (complex to test)

**View Coverage:**
```bash
pytest --cov=scholardoc_ocr --cov-report=html tests/
# Opens htmlcov/index.html in browser
```

## Test Types

**Unit Tests:**
- **Scope:** Individual functions/methods (QualityAnalyzer.analyze, PDFProcessor.extract_text)
- **Approach:**
  - Test single responsibility per test method
  - Use fixtures for setup
  - Mock external dependencies (file I/O, external libraries)
  - Keep tests fast (< 100ms per test)

**Example (for `quality.py`):**
```python
def test_quality_analyzer_flags_heavily_garbled_text(quality_analyzer):
    """Pages with >30% garbled words should be flagged."""
    text = "word1 word2 aaaaaa bbbbbb cccccc dddddd eeeeee " * 10
    result = quality_analyzer.analyze(text)

    assert result.flagged is True
    assert result.garbled_count > 0
    assert result.score < 0.85  # Below threshold

def test_quality_analyzer_accepts_german_philosophical_terms(quality_analyzer):
    """German philosophical terms should not be marked as garbled."""
    text = "Heidegger discusses Dasein and Befindlichkeit extensively."
    result = quality_analyzer.analyze(text)

    assert result.garbled_count == 0
    assert result.flagged is False
```

**Integration Tests:**
- **Scope:** Multiple components working together (e.g., pipeline phases)
- **Approach:**
  - Use temporary PDF files (created in setup)
  - Test actual workflow: Tesseract → Quality Check → (Optional) Surya
  - Mock external heavy operations (actual Tesseract/Surya runs)
  - Verify results are correct and files created

**Example:**
```python
@pytest.mark.integration
def test_pipeline_phases_work_together(tmp_path):
    """Test that Phase 1 (Tesseract) and Phase 2 (Surya) integrate correctly."""
    # This would require a real PDF and would be slower
    # Typically marked with @pytest.mark.integration and run separately
    pass
```

**E2E Tests:**
- **Status:** Not present; would be expensive (load Surya models)
- **Framework:** Could use pytest with real PDFs if needed
- **Suggested approach:** Run on CI only, skip in local development
- **Markers:** Use `@pytest.mark.e2e` to isolate from fast unit tests

## Common Patterns

**Async Testing:**
- Not applicable (no async code in codebase)
- Pipeline uses `ProcessPoolExecutor` (synchronous, returns `Future` objects)

**Error Testing:**
```python
def test_extract_text_from_missing_file_returns_empty_string():
    """Missing files should return empty string, not raise."""
    processor = PDFProcessor()
    result = processor.extract_text(Path("/nonexistent/file.pdf"))

    assert result == ""
    # Verify logger.warning was called
    assert "failed" in result.lower()  # Or use mock to verify logging

def test_tesseract_timeout_is_handled():
    """Tesseract timeouts should be caught gracefully."""
    with patch('scholardoc_ocr.processor.subprocess.run') as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ocrmypdf", timeout=600)

        processor = PDFProcessor()
        result = processor.run_tesseract(Path("test.pdf"), Path("out.pdf"))

        assert result is False  # Returns False, doesn't raise
```

**Quality Analysis Testing:**
```python
def test_quality_analyzer_detects_control_characters():
    """Control characters should be flagged as garbled."""
    text = "This text has \x00 null character embedded."
    analyzer = QualityAnalyzer()
    result = analyzer.analyze(text)

    assert result.garbled_count > 0
    assert result.flagged is True

def test_quality_analyzer_ignores_valid_references():
    """Page numbers and references should not be flagged."""
    text = "Page 123 and footnote [1] are valid. ISBN-123-456-789 is also valid."
    analyzer = QualityAnalyzer()
    result = analyzer.analyze(text)

    assert result.garbled_count < 2
```

## Notes on Testing Strategy

**Why tests don't exist yet:**
- Project is new (initial commit: 2024)
- Focus has been on core pipeline functionality
- Heavy reliance on external tools (Tesseract, Surya) makes testing complex

**Testing challenges:**
- Tesseract requires subprocess calls (slow, needs mocking)
- Surya loads large ML models (expensive, should mock in unit tests)
- PDF operations need real or synthetic PDFs
- Quality analysis has many edge cases (German terms, Greek transliterations, etc.)

**Recommended test implementation priority:**
1. **Quality analyzer unit tests** (no external dependencies, fast feedback)
2. **Processor method tests** (mock external tools)
3. **Pipeline integration tests** (combine components)
4. **CLI tests** (argument parsing and validation)
5. **End-to-end tests** (full pipeline with sample files, on CI only)

---

*Testing analysis: 2026-01-28*
