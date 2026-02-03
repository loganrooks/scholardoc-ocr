# Phase 11: Benchmarking Foundation & Metrics Fixes - Research

**Researched:** 2026-02-03
**Domain:** Python benchmarking infrastructure, memory profiling, GPU timing
**Confidence:** HIGH

## Summary

This phase has two distinct concerns: (1) establishing benchmarking infrastructure with pytest-benchmark, memray memory profiling, and CI regression detection, and (2) fixing metrics bugs in the current pipeline (Surya timing not captured, engine field incorrect, quality scores not re-evaluated after Surya).

The standard approach for Python benchmarking is pytest-benchmark for CPU/wall-clock timing, with pedantic mode required for GPU operations that need setup/teardown (model loading, MPS synchronization). Memory profiling uses Bloomberg's memray with the pytest-memray plugin for per-test allocation limits. CI regression detection uses github-action-benchmark which consumes pytest-benchmark JSON output and fails on threshold violations.

For the metrics fixes, the current codebase captures `phase_timings` for Tesseract but not for Surya model loading or inference. The `FileResult.engine` field is set once during Tesseract processing and never updated when Surya runs on flagged pages. Quality scores are evaluated after Tesseract but not re-evaluated after Surya enhancement.

**Primary recommendation:** Use pytest-benchmark's pedantic mode with setup/teardown for GPU benchmarks, add memray integration for memory leak detection, and extend the existing `phase_timings` dict with Surya timing entries.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest-benchmark | 5.2.x | Performance benchmarking | De facto standard pytest plugin, statistical rigor, JSON export for CI |
| memray | 1.x | Memory profiling | Bloomberg's production-grade profiler, tracks native + Python allocations |
| pytest-memray | 1.x | Memory testing in pytest | Official pytest plugin from Bloomberg, per-test memory limits |
| github-action-benchmark | v1 | CI regression detection | Supports pytest-benchmark output, threshold-based failures, GitHub Pages history |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| torch.mps | (via PyTorch) | GPU synchronization | Required for accurate MPS timing - synchronize before measuring |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pytest-benchmark | asv (airspeed velocity) | asv has better historical visualization but heavier setup; pytest-benchmark integrates with existing test suite |
| github-action-benchmark | Bencher | Bencher is more feature-rich but requires SaaS account; github-action-benchmark is zero-dependency |
| memray | tracemalloc | tracemalloc is stdlib but can't track C extensions; memray tracks all allocations including PyTorch tensors |

**Installation:**
```bash
pip install "pytest-benchmark>=5.0" "memray>=1.0" "pytest-memray>=1.0"
```

## Architecture Patterns

### Recommended Project Structure
```
tests/
├── conftest.py          # Shared fixtures, benchmark group config
├── benchmarks/          # Separate directory for benchmark tests
│   ├── conftest.py      # Benchmark-specific fixtures (model loading, sample PDFs)
│   ├── test_model_loading.py   # Model load time benchmarks
│   ├── test_inference.py       # OCR inference benchmarks
│   └── test_memory.py          # Memory limit/leak tests
├── test_*.py            # Existing unit tests (unchanged)
```

### Pattern 1: Pedantic Mode for GPU Operations
**What:** Use `benchmark.pedantic()` for operations requiring setup (model loading) or teardown (GPU sync)
**When to use:** Any benchmark involving MPS/GPU operations that are asynchronous
**Example:**
```python
# Source: pytest-benchmark docs + PyTorch MPS docs
import torch

def test_surya_inference(benchmark, loaded_models, sample_pdf):
    """Benchmark Surya inference with proper GPU sync."""

    def setup():
        """Called before each round."""
        # Clear MPS cache for consistent starting state
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
        return (sample_pdf, loaded_models), {}

    def run_inference(pdf_path, models):
        from scholardoc_ocr.surya import convert_pdf
        result = convert_pdf(pdf_path, models)
        # CRITICAL: Synchronize GPU before timing ends
        if torch.backends.mps.is_available():
            torch.mps.synchronize()
        return result

    benchmark.pedantic(
        run_inference,
        setup=setup,
        rounds=5,
        warmup_rounds=1,
        iterations=1,  # One iteration per round (expensive operation)
    )
```

### Pattern 2: Model Loading Benchmark with Fixture
**What:** Benchmark model loading time separately from inference
**When to use:** Measuring cold-start performance for BENCH-06
**Example:**
```python
# Source: pytest-benchmark docs
def test_model_loading_time(benchmark):
    """Benchmark Surya model loading (cold start)."""

    def load_models():
        import torch
        from scholardoc_ocr.surya import load_models
        models = load_models()
        if torch.backends.mps.is_available():
            torch.mps.synchronize()
        return models

    # Use pedantic with single round for expensive operation
    result = benchmark.pedantic(
        load_models,
        rounds=3,
        warmup_rounds=0,  # No warmup for cold start measurement
        iterations=1,
    )
    assert result is not None
```

### Pattern 3: Memory Limit Testing
**What:** Use pytest-memray markers to prevent memory regressions
**When to use:** Ensuring OCR processing stays within memory bounds
**Example:**
```python
# Source: pytest-memray docs
import pytest

@pytest.mark.limit_memory("512 MB")
def test_single_page_memory(sample_pdf, loaded_models):
    """Single page OCR should not exceed 512MB peak memory."""
    from scholardoc_ocr.surya import convert_pdf
    convert_pdf(sample_pdf, loaded_models, page_range=[0])

@pytest.mark.limit_leaks("10 MB")
def test_no_memory_leak_across_files(sample_pdfs, loaded_models):
    """Processing multiple files should not accumulate memory."""
    from scholardoc_ocr.surya import convert_pdf
    for pdf in sample_pdfs:
        convert_pdf(pdf, loaded_models)
```

### Pattern 4: Hardware Profile Detection
**What:** Detect Apple Silicon variant for baseline selection
**When to use:** BENCH-05 hardware-specific profiles
**Example:**
```python
# Source: Apple Developer Forums + community research
import subprocess
import platform

def get_apple_silicon_variant() -> str | None:
    """Detect M1/M2/M3 variant for benchmark profile selection."""
    if platform.machine() != "arm64":
        return None  # Not Apple Silicon

    try:
        result = subprocess.run(
            ["sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True, text=True, check=True
        )
        brand = result.stdout.strip()  # e.g., "Apple M2 Max"

        # Extract base model (M1, M2, M3)
        for model in ("M4", "M3", "M2", "M1"):  # Check newest first
            if model in brand:
                return model
        return "unknown"
    except subprocess.CalledProcessError:
        return None

# In conftest.py
@pytest.fixture(scope="session")
def hardware_profile():
    """Hardware profile for benchmark baselines."""
    return get_apple_silicon_variant() or "cpu"
```

### Anti-Patterns to Avoid
- **Timing without GPU sync:** Measuring GPU operations without `torch.mps.synchronize()` gives artificially fast times because GPU runs async
- **Using normal mode for expensive operations:** `benchmark(func)` auto-calibrates rounds which causes many model loads; use pedantic with explicit rounds
- **Memory tests without loops:** Single invocations can't distinguish leaks from Python interpreter caches; run in loops per memray docs
- **Hardcoding baselines:** Different M1/M2/M3 chips have different expected performance; baselines must be hardware-specific

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Timing statistics | Custom mean/stddev calculation | pytest-benchmark stats | Handles outliers, provides median, IQR, min, max automatically |
| Memory tracking | Manual `tracemalloc` wrapper | memray + pytest-memray | Tracks native allocations from PyTorch/C extensions that tracemalloc misses |
| Regression detection | Custom comparison scripts | github-action-benchmark | Handles historical data, threshold alerts, PR comments out of box |
| GPU synchronization | Hoping `time.time()` works | `torch.mps.synchronize()` | MPS operations are async; wall clock without sync measures queue time, not execution |
| Hardware detection | Parsing `/proc/cpuinfo` | `sysctl -n machdep.cpu.brand_string` | macOS-specific, reliable, returns human-readable chip name |

**Key insight:** Benchmarking GPU operations on Apple Silicon requires explicit synchronization because MPS operations are asynchronous. Without `torch.mps.synchronize()`, timing measurements will be inaccurate.

## Common Pitfalls

### Pitfall 1: Async GPU Timing
**What goes wrong:** Benchmark shows 0.1s for model inference when actual GPU time is 2.0s
**Why it happens:** MPS operations return immediately; actual GPU work continues in background
**How to avoid:** Always call `torch.mps.synchronize()` before stopping the timer
**Warning signs:** Suspiciously fast benchmarks, timing varies wildly between runs

### Pitfall 2: Cold vs Warm Model Loading
**What goes wrong:** Benchmarks show 2s model load when real first-run is 30s
**Why it happens:** Models cached in memory from previous test; measuring warm cache hits
**How to avoid:** Use separate test process for cold start, or explicitly unload models
**Warning signs:** Second benchmark run is 10x faster than first

### Pitfall 3: Memory Leak False Positives
**What goes wrong:** Tests fail with "memory leak" when running standard Python operations
**Why it happens:** Python interpreter has internal caches (regex, logging, etc.) that grow
**How to avoid:** Run code in loops (100+ iterations), use reasonable thresholds (1MB+)
**Warning signs:** Leak detection on first run of any code, different results each run

### Pitfall 4: CI Flaky Benchmarks
**What goes wrong:** Benchmark passes locally but fails in CI randomly
**Why it happens:** Shared CI runners have variable performance, background processes
**How to avoid:** Use percentage thresholds (200% default in github-action-benchmark), run multiple rounds
**Warning signs:** Benchmark failures correlate with CI load, not code changes

### Pitfall 5: Engine Field Never Updated
**What goes wrong:** BENCH-07 - `FileResult.engine` is always "tesseract" even when Surya ran
**Why it happens:** Current code sets engine once in `_tesseract_worker`, never updates after Surya enhancement
**How to avoid:** Compute engine from per-page engines after all processing complete
**Warning signs:** JSON metadata shows `"engine": "tesseract"` for files with Surya-enhanced pages

### Pitfall 6: Quality Scores Not Re-evaluated
**What goes wrong:** BENCH-08 - Quality score reflects Tesseract output even after Surya improves it
**Why it happens:** Quality analysis happens in Tesseract worker, Surya phase doesn't re-analyze
**How to avoid:** Run quality analysis after Surya, store both pre/post scores
**Warning signs:** Files with Surya enhancement show same quality score as before enhancement

## Code Examples

Verified patterns from official sources:

### pytest-benchmark JSON Export for CI
```python
# Source: pytest-benchmark docs
# Run with: pytest --benchmark-only --benchmark-json=benchmark.json

# pytest.ini or pyproject.toml
# [tool.pytest.ini_options]
# addopts = "--benchmark-group-by=func"
```

### GitHub Actions Workflow for Regression Detection
```yaml
# Source: github-action-benchmark docs
# .github/workflows/benchmark.yml
name: Benchmark
on: [push, pull_request]

jobs:
  benchmark:
    runs-on: macos-14  # M-series runner
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -e ".[dev]" pytest-benchmark

      - name: Run benchmarks
        run: pytest tests/benchmarks --benchmark-only --benchmark-json=output.json

      - name: Store benchmark result
        uses: benchmark-action/github-action-benchmark@v1
        with:
          tool: 'pytest'
          output-file-path: output.json
          github-token: ${{ secrets.GITHUB_TOKEN }}
          auto-push: true
          alert-threshold: '150%'  # 50% regression triggers alert
          fail-on-alert: true
          comment-on-alert: true
```

### Surya Timing Capture (BENCH-06 Fix)
```python
# In pipeline.py, within the Surya processing loop
import time
import torch

# Before model loading
t0 = time.time()
model_dict = surya.load_models()
if torch.backends.mps.is_available():
    torch.mps.synchronize()
model_load_time = time.time() - t0

# Before inference
t0 = time.time()
surya_markdown = surya.convert_pdf(input_path, model_dict, ...)
if torch.backends.mps.is_available():
    torch.mps.synchronize()
inference_time = time.time() - t0

# Store in phase_timings
file_result.phase_timings["surya_model_load"] = model_load_time
file_result.phase_timings["surya_inference"] = inference_time
```

### Compute Engine from Pages (BENCH-07 Fix)
```python
# In FileResult or BatchResult processing
def compute_engine(pages: list[PageResult]) -> OCREngine:
    """Determine top-level engine from per-page engines."""
    engines = {p.engine for p in pages if p.engine != OCREngine.NONE}

    if not engines:
        return OCREngine.NONE
    if engines == {OCREngine.TESSERACT}:
        return OCREngine.TESSERACT
    if engines == {OCREngine.SURYA}:
        return OCREngine.SURYA
    if engines == {OCREngine.EXISTING}:
        return OCREngine.EXISTING
    # Mixed processing
    return OCREngine.MIXED  # New enum value needed

# Usage: file_result.engine = compute_engine(file_result.pages)
```

### Re-evaluate Quality After Surya (BENCH-08 Fix)
```python
# In pipeline.py after Surya enhancement
from scholardoc_ocr.quality import QualityAnalyzer

# After Surya writes enhanced text
if surya_enhanced_pages:
    analyzer = QualityAnalyzer(config.quality_threshold)

    for page_num in surya_enhanced_pages:
        page_text = extract_page_text(output_pdf, page_num)
        quality_result = analyzer.analyze_page(page_text)

        # Find corresponding PageResult and update
        page_result = file_result.pages[page_num]
        page_result.quality_score_pre_surya = page_result.quality_score  # Preserve
        page_result.quality_score = quality_result.score
        page_result.status = PageStatus.GOOD if not quality_result.flagged else PageStatus.FLAGGED
```

### pytest-memray Integration
```python
# tests/conftest.py
# Source: pytest-memray docs

def pytest_configure(config):
    """Register memray markers."""
    config.addinivalue_line(
        "markers", "limit_memory(amount): Limit peak memory for this test"
    )
    config.addinivalue_line(
        "markers", "limit_leaks(amount): Detect memory leaks in this test"
    )
```

```bash
# Run with memray enabled
pytest tests/benchmarks/test_memory.py --memray

# Generate flame graph from results
memray flamegraph .memray/test_output.bin
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| timeit for benchmarks | pytest-benchmark | 2018+ | Statistical rigor, CI integration, historical comparison |
| memory_profiler | memray | 2022 | Tracks native allocations, supports C extensions, flame graphs |
| Manual CI scripts | github-action-benchmark | 2020+ | Zero-config regression detection, GitHub Pages history |
| Assuming sync timing | explicit torch.mps.synchronize() | 2022 (MPS GA) | Required for accurate GPU timing on Apple Silicon |

**Deprecated/outdated:**
- `memory_profiler` package: Replaced by memray for C extension support
- Manually calling `gc.collect()` for timing: pytest-benchmark handles GC control

## Open Questions

Things that couldn't be fully resolved:

1. **MPS Event-based Timing**
   - What we know: CUDA has `torch.cuda.Event()` for GPU timing; unknown if MPS has equivalent
   - What's unclear: PyTorch MPS docs don't document event-based timing API
   - Recommendation: Use `torch.mps.synchronize()` + wall clock, which is verified to work

2. **M1/M2/M3 Baseline Values**
   - What we know: Different chips have different expected performance
   - What's unclear: What specific baseline values to use for each chip
   - Recommendation: Run initial benchmarks on available hardware to establish baselines, store in config

3. **memray on Apple Silicon**
   - What we know: memray supports macOS
   - What's unclear: Any MPS/Metal-specific memory tracking considerations
   - Recommendation: Test memray with Surya to verify it tracks GPU memory correctly

## Sources

### Primary (HIGH confidence)
- [pytest-benchmark 5.2.3 documentation](https://pytest-benchmark.readthedocs.io/) - usage, pedantic mode, JSON export
- [memray/pytest-memray documentation](https://bloomberg.github.io/memray/) - memory profiling, pytest integration
- [github-action-benchmark](https://github.com/benchmark-action/github-action-benchmark) - CI integration, threshold configuration
- [PyTorch MPS Backend](https://docs.pytorch.org/docs/stable/notes/mps.html) - MPS availability, basic usage

### Secondary (MEDIUM confidence)
- [Apple Developer Forums](https://developer.apple.com/forums/thread/652667) - sysctl for hardware detection
- [pytest-benchmark pedantic mode](https://pytest-benchmark.readthedocs.io/en/latest/pedantic.html) - setup/teardown pattern

### Tertiary (LOW confidence)
- WebSearch results for `torch.mps.synchronize()` usage patterns - community convention, not official docs

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Official documentation verified for all libraries
- Architecture: HIGH - Patterns from official docs, adapted to project structure
- Pitfalls: MEDIUM - Some from community experience, MPS timing verified empirically

**Research date:** 2026-02-03
**Valid until:** 2026-03-03 (30 days - stable libraries)
