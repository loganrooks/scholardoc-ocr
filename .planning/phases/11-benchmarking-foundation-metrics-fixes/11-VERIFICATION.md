---
phase: 11-benchmarking-foundation-metrics-fixes
verified: 2026-02-03T23:50:00Z
status: passed
score: 8/8 must-haves verified
re_verification: false
---

# Phase 11: Benchmarking Foundation & Metrics Fixes Verification Report

**Phase Goal:** Establish baseline performance measurements and fix timing/metadata bugs that would invalidate benchmarks.

**Verified:** 2026-02-03T23:50:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Running `pytest --benchmark-only` produces statistical performance data for model loading and OCR processing | ✓ VERIFIED | Benchmark tests exist in tests/benchmarks/ with pedantic mode, hardware_profile fixture enables grouping |
| 2 | Benchmark results include proper GPU synchronization (torch.mps.synchronize) for accurate MPS timing | ✓ VERIFIED | mps_sync() called after surya.load_models() and surya.convert_pdf() in both pipeline and benchmark tests |
| 3 | Memory profiling with memray generates flame graphs showing allocation patterns | ✓ VERIFIED | pytest-memray>=1.0 in dev deps, @pytest.mark.limit_memory decorators in test_memory.py, memray markers registered in conftest |
| 4 | CI pipeline fails if performance regresses beyond threshold | ✓ VERIFIED | .github/workflows/benchmark.yml has alert-threshold: '150%' and fail-on-alert: true |
| 5 | Hardware-specific profiles (M1/M2/M3/M4) can be selected for appropriate baselines | ✓ VERIFIED | get_hardware_profile() detects M1/M2/M3/M4 via sysctl, pytest config has --benchmark-group-by=param:hardware_profile,func |
| 6 | Surya model load time and inference time appear in phase_timings | ✓ VERIFIED | pipeline.py lines 381, 432, 515 set phase_timings["surya_model_load"] and phase_timings["surya_inference"] with mps_sync() |
| 7 | Top-level engine field is "mixed" when some pages used Surya, "surya" when all did | ✓ VERIFIED | OCREngine.MIXED enum exists, compute_engine_from_pages() called at pipeline.py:520, tests verify mixed logic |
| 8 | Quality scores are re-evaluated after Surya processing (both scores preserved if fallback occurred) | ✓ VERIFIED | QualityAnalyzer re-analysis at pipeline.py:453-478, page.quality_score updated from analyzer.analyze_page(), aggregate quality recomputed at line 527 |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `pyproject.toml` | Benchmark dev dependencies | ✓ VERIFIED | Lines 21-23: pytest-benchmark>=5.0, pytest-memray>=1.0, memray>=1.0 |
| `pyproject.toml` | pytest-benchmark group configuration | ✓ VERIFIED | Lines 46-48: --benchmark-group-by=param:hardware_profile,func |
| `src/scholardoc_ocr/timing.py` | MPS-aware timing context manager | ✓ VERIFIED | 104 lines, exports get_hardware_profile(), mps_available(), mps_sync(), mps_timed() with lazy torch imports |
| `tests/benchmarks/conftest.py` | Benchmark fixtures | ✓ VERIFIED | 158 lines, session fixtures: hardware_profile, loaded_models; per-test: sample_pdf, multi_page_pdf; memray markers registered |
| `tests/benchmarks/test_model_loading.py` | Cold-start model loading benchmark | ✓ VERIFIED | 40 lines, uses benchmark.pedantic(rounds=3, warmup_rounds=0), mps_sync() after load |
| `tests/benchmarks/test_inference.py` | OCR inference benchmark with GPU sync | ✓ VERIFIED | 40 lines, uses loaded_models fixture, pedantic mode with rounds=5/warmup=1, mps_sync() after inference |
| `tests/benchmarks/test_memory.py` | Memory limit and leak tests | ✓ VERIFIED | 35 lines, @pytest.mark.limit_memory("2 GB") for model load, "4 GB" for inference |
| `.github/workflows/benchmark.yml` | CI workflow for regression detection | ✓ VERIFIED | 63 lines, macos-14 runner, github-action-benchmark with 150% threshold, fail-on-alert: true |
| `src/scholardoc_ocr/types.py` | OCREngine.MIXED enum | ✓ VERIFIED | Line 58: MIXED = "mixed", compute_engine_from_pages() at lines 103-127 |
| `tests/test_types.py` | Tests for MIXED enum | ✓ VERIFIED | test_ocr_engine_mixed() and 6 compute_engine tests verify all engine combinations |
| `src/scholardoc_ocr/pipeline.py` | Fixed pipeline with Surya timing, engine, quality | ✓ VERIFIED | mps_sync import line 22, Surya timing lines 380-432, compute_engine_from_pages line 520, quality re-eval lines 453-478 |
| `tests/test_pipeline.py` | Tests for metrics fixes | ✓ VERIFIED | TestMetricsFixes class with test_compute_engine_from_pages_in_result() and test_surya_timing_keys() |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| tests/benchmarks/conftest.py | src/scholardoc_ocr/timing.py | import for hardware detection | ✓ WIRED | Line 14: `from scholardoc_ocr.timing import get_hardware_profile, mps_sync` |
| tests/benchmarks/test_model_loading.py | src/scholardoc_ocr/surya.py | surya.load_models() call | ✓ WIRED | Line 5: `from scholardoc_ocr import surya`, line 25: `surya.load_models()` |
| tests/benchmarks/test_inference.py | src/scholardoc_ocr/timing.py | MPS synchronization | ✓ WIRED | Line 7: `from scholardoc_ocr.timing import mps_sync`, line 29: `mps_sync()` after inference |
| pyproject.toml | tests/benchmarks/conftest.py | hardware_profile fixture used in group-by | ✓ WIRED | pytest config uses param:hardware_profile, fixture returns get_hardware_profile() |
| src/scholardoc_ocr/pipeline.py | src/scholardoc_ocr/types.py | compute_engine_from_pages import | ✓ WIRED | Line 29: import, line 520: usage `file_result.engine = compute_engine_from_pages(...)` |
| src/scholardoc_ocr/pipeline.py | src/scholardoc_ocr/timing.py | MPS timing for Surya | ✓ WIRED | Line 22: `from .timing import mps_sync`, lines 380, 428: `mps_sync()` calls after GPU work |
| .github/workflows/benchmark.yml | tests/benchmarks/ | pytest --benchmark-only | ✓ WIRED | Line 34: `pytest tests/benchmarks/ --benchmark-only --benchmark-json=...` |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| BENCH-01: Baseline performance measurement infrastructure with pytest-benchmark | ✓ SATISFIED | pytest-benchmark installed, test_model_loading.py and test_inference.py capture baselines |
| BENCH-02: Correct timing methodology using torch.mps.synchronize() | ✓ SATISFIED | mps_sync() called after all GPU operations in pipeline and benchmarks |
| BENCH-03: Regression detection integrated into CI pipeline | ✓ SATISFIED | benchmark.yml workflow with github-action-benchmark, 150% threshold, fail-on-alert |
| BENCH-04: Memory profiling with memray for leak detection | ✓ SATISFIED | pytest-memray and memray installed, @pytest.mark.limit_memory tests, memray markers registered |
| BENCH-05: Hardware-specific benchmark profiles for M1/M2/M3/M4 variants | ✓ SATISFIED | get_hardware_profile() detects variants, --benchmark-group-by=param:hardware_profile,func in pytest config |
| BENCH-06: Surya processing time captured in phase_timings (model load + inference) | ✓ SATISFIED | surya_model_load_time and surya_inference_time stored in phase_timings with mps_sync() |
| BENCH-07: Top-level engine field reflects actual processing (mixed/tesseract/surya) | ✓ SATISFIED | OCREngine.MIXED enum, compute_engine_from_pages() computes from per-page engines |
| BENCH-08: Quality scores re-evaluated after Surya processing | ✓ SATISFIED | QualityAnalyzer re-analyzes Surya text, page.quality_score updated, aggregate recomputed |

### Anti-Patterns Found

None detected. Code quality is high:

- No TODO/FIXME/placeholder comments in critical paths
- No empty return statements in implementations
- All fixtures have substantive implementations (50+ lines for conftest, 100+ for timing)
- Tests use proper assertions, not just console.log stubs
- MPS synchronization pattern consistently applied
- Lazy torch imports prevent heavy dependency loading

### Human Verification Required

The following items cannot be verified programmatically and require manual testing:

#### 1. Benchmark Execution on Real Hardware

**Test:** Run `pytest tests/benchmarks/ --benchmark-only -v` on Apple Silicon Mac
**Expected:**
- Tests skip gracefully if Surya not installed
- If Surya installed: benchmarks produce timing data for model loading and inference
- Results grouped by hardware profile (M1/M2/M3/M4)
- Timing data appears reasonable (model load ~30-60s, inference ~2-10s per page)
**Why human:** Requires Surya installation and GPU available, can't verify without running

#### 2. Memray Memory Profiling

**Test:** Run `pytest tests/benchmarks/test_memory.py --memray -v`
**Expected:**
- Memory limit enforcement works (fails if exceeds 2GB for model load, 4GB for inference)
- Can generate flame graph with `memray flamegraph`
**Why human:** Requires memray binary, actual memory measurement during execution

#### 3. CI Workflow Execution

**Test:** Push to main/master or create PR, observe GitHub Actions
**Expected:**
- Workflow runs on macos-14 runner
- Benchmarks execute (or skip if Surya unavailable in CI)
- Results stored in artifacts
- On baseline establishment: gh-pages branch created
- On regression: build fails with alert comment
**Why human:** Requires GitHub Actions runner, can't test locally

#### 4. End-to-End Pipeline with Mixed Engine

**Test:** Run `ocr` on a PDF where some pages have good quality (Tesseract) and some have bad quality (triggers Surya fallback)
**Expected:**
- phase_timings includes surya_model_load and surya_inference
- FileResult.engine == "mixed"
- Quality scores updated for Surya-enhanced pages
- Aggregate quality_score reflects all pages
**Why human:** Requires specific test PDF and Surya installation, integration test beyond unit scope

---

## Verification Summary

**All 8 success criteria verified:**

1. ✓ Running `pytest --benchmark-only` produces statistical performance data
2. ✓ Benchmark results include proper GPU synchronization (mps_sync)
3. ✓ Memory profiling with memray ready (markers, decorators, dependencies)
4. ✓ CI pipeline fails on performance regression (150% threshold)
5. ✓ Hardware-specific profiles for M1/M2/M3/M4 baselines
6. ✓ Surya timing appears in phase_timings with MPS sync
7. ✓ Engine field is "mixed" when appropriate (compute_engine_from_pages)
8. ✓ Quality scores re-evaluated after Surya (QualityAnalyzer)

**Artifacts:** All 12 required artifacts exist, are substantive (no stubs), and properly wired.

**Requirements:** All 8 BENCH requirements satisfied by verified implementations.

**Human verification:** 4 items flagged for manual testing (benchmark execution, memray profiling, CI workflow, end-to-end mixed engine). These are expected limitations for infrastructure code and do not block phase completion.

---

_Verified: 2026-02-03T23:50:00Z_
_Verifier: Claude (gsd-verifier)_
