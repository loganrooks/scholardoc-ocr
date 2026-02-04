---
phase: 12-device-configuration
verified: 2026-02-04T12:00:00Z
status: passed
score: 4/4 must-haves verified
---

# Phase 12: Device Configuration Verification Report

**Phase Goal:** Enable explicit MPS device selection with validation and fallback for Apple Silicon GPU acceleration.
**Verified:** 2026-02-04T12:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Pipeline explicitly uses MPS device on Apple Silicon (visible in logs: "Using device: mps") | ✓ VERIFIED | device.py:110 logs "Using device: mps (Apple Silicon)", surya.py:80 logs device info from detect_device() |
| 2 | Startup validates MPS availability and shows actionable error if unavailable | ✓ VERIFIED | environment.py:20-46 check_gpu_availability() returns (bool, message) with actionable explanations, cli.py:314-319 shows GPU status in verbose mode |
| 3 | Processing automatically falls back to CPU when MPS fails mid-job | ✓ VERIFIED | surya.py:153-221 convert_pdf_with_fallback() catches RuntimeError, reloads models on CPU, retries conversion. pipeline.py:428-449 integrates fallback and tracks in results |
| 4 | MPS bugs are handled via full-CPU fallback (detection/recognition split deferred) | ✓ VERIFIED | convert_pdf_with_fallback() retries entire batch on CPU (line 214), not split by model. Marker API uses unified device per model_dict |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/scholardoc_ocr/device.py` | Device detection with validation | ✓ VERIFIED | 170 lines, exports DeviceType, DeviceInfo, detect_device(). Validates CUDA/MPS/CPU with test tensor allocation. No stubs. |
| `src/scholardoc_ocr/surya.py` | convert_pdf_with_fallback function | ✓ VERIFIED | Lines 153-221, full implementation with OOM recovery outside except block (lines 197-215). Returns (str, bool) tuple. Integrated with load_models() for CPU retry. |
| `src/scholardoc_ocr/pipeline.py` | Uses convert_pdf_with_fallback | ✓ VERIFIED | Line 428 calls convert_pdf_with_fallback, lines 442-449 track fallback in results, update device_used to "cpu" |
| `src/scholardoc_ocr/environment.py` | check_gpu_availability function | ✓ VERIFIED | Lines 20-46, returns (bool, message) with actionable status for CUDA/MPS/CPU. Lazy torch import. Integrated in log_startup_diagnostics (line 154) |
| `src/scholardoc_ocr/cli.py` | --strict-gpu flag | ✓ VERIFIED | Lines 192-195 argparse definition, line 357 propagates to PipelineConfig, lines 316-319 show GPU status when verbose |
| `tests/test_device.py` | Test coverage for fallback | ✓ VERIFIED | Lines 255-354 TestConvertPdfWithFallback class with 5 tests covering existence, fallback behavior, strict_gpu, success path, return type |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| pipeline.py | surya.convert_pdf_with_fallback | Function call | ✓ WIRED | Line 428 calls with input_path, model_dict, config, page_range, strict_gpu. Response tuple unpacked (markdown, fallback_occurred) |
| convert_pdf_with_fallback | surya.load_models | CPU retry | ✓ WIRED | Line 213 calls load_models(device="cpu") on fallback path, assigns to cpu_model_dict |
| convert_pdf_with_fallback | convert_pdf | GPU attempt + CPU retry | ✓ WIRED | Line 184 initial GPU call, line 214 CPU retry. Both use convert_pdf() with different model_dicts |
| surya.load_models | device.detect_device | Auto-detection | ✓ WIRED | Lines 76-80 import detect_device and use device_info.device_type when device arg is None |
| pipeline | FileResult.device_used | Fallback tracking | ✓ WIRED | Line 448 sets file_result.device_used = "cpu" when fallback_occurred is True, line 449 sets phase_timings["surya_fallback"] = True |
| cli | environment.check_gpu_availability | Verbose startup | ✓ WIRED | Lines 316-319 import and call check_gpu_availability in verbose mode, display via Rich console |
| cli | PipelineConfig.strict_gpu | Flag propagation | ✓ WIRED | Line 357 strict_gpu=args.strict_gpu, field defined in pipeline.py:44 |

### Requirements Coverage

| Requirement | Status | Supporting Evidence |
|-------------|--------|---------------------|
| DEV-01: Pipeline explicitly selects MPS device | ✓ SATISFIED | device.py detect_device() with CUDA > MPS > CPU priority, surya.py load_models() uses detect_device() when device=None, logs "Using device: mps" |
| DEV-02: Startup validation with actionable errors | ✓ SATISFIED | environment.py check_gpu_availability() with actionable messages ("MPS built but not available (macOS < 12.3 or no GPU)"), cli.py shows in verbose mode |
| DEV-03: Automatic CPU fallback on failure | ✓ SATISFIED | convert_pdf_with_fallback() catches RuntimeError, reloads models on CPU, retries conversion. Warning logged at line 209-212 |
| DEV-04: Per-model device selection for MPS bugs | ✓ SATISFIED (via full-CPU fallback) | Implementation uses full-CPU fallback strategy (entire batch on CPU) rather than detection/recognition split. Plan 12-05 SUMMARY notes this approach, deferring split until Marker API supports per-model device |

### Anti-Patterns Found

None detected.

**Scan results:**
- No TODO/FIXME/XXX/HACK comments in device.py, surya.py, environment.py
- No placeholder text or stub patterns
- No empty returns or console.log-only implementations
- All functions have substantive implementations with proper error handling
- Test coverage comprehensive (29 tests in test_device.py)

### Human Verification Required

#### 1. MPS Device Selection on Apple Silicon

**Test:** Run `ocr --verbose ~/test.pdf` on an Apple Silicon Mac with MPS available
**Expected:** 
- Console output shows "GPU: MPS available (Apple Silicon)"
- Log shows "Using device: mps (Apple Silicon)"
- Log shows "Loading Surya/Marker models on device: mps"
**Why human:** Requires Apple Silicon hardware and actual Surya model loading

#### 2. GPU Fallback Behavior

**Test:** On MPS-enabled system, trigger an MPS failure (e.g., via known MPS bug in Surya detection)
**Expected:**
- Initial attempt uses MPS device
- On failure, log shows WARNING "GPU inference failed, retrying on CPU: {error}"
- Processing completes successfully on CPU
- Result metadata shows device_used="cpu" and surya_fallback=True
**Why human:** Requires triggering actual MPS failure conditions

#### 3. Strict GPU Mode

**Test:** Run `ocr --strict-gpu ~/test.pdf` on a CPU-only system or when GPU fails
**Expected:**
- Processing fails with SuryaError
- Error message contains "strict_gpu=True"
- Does NOT fall back to CPU
**Why human:** Requires controlled environment without GPU or with failing GPU

#### 4. Startup Diagnostics Clarity

**Test:** Run `ocr --help` and `ocr --verbose ~/test.pdf` on different systems (MPS, CUDA, CPU-only)
**Expected:**
- `--help` shows clear description of --strict-gpu flag
- Verbose mode shows appropriate GPU message for each platform:
  - Apple Silicon with MPS: "GPU: MPS available (Apple Silicon)"
  - CUDA system: "GPU: CUDA available: {device_name}"
  - CPU-only: "GPU: GPU not available, will use CPU"
  - MPS-built but unavailable: "GPU: MPS built but not available (macOS < 12.3 or no GPU)"
**Why human:** Requires testing across different hardware platforms

## Verification Details

### Artifact Verification (3-Level Check)

**Level 1: Existence** — All artifacts exist
- device.py: 170 lines
- surya.py: 222 lines (convert_pdf_with_fallback at 153-221)
- environment.py: 156 lines (check_gpu_availability at 20-46)
- pipeline.py: modified (strict_gpu field + fallback integration)
- cli.py: modified (--strict-gpu flag + verbose GPU display)
- tests/test_device.py: 354+ lines

**Level 2: Substantive** — All implementations complete
- device.py: Full DeviceType enum, DeviceInfo dataclass, detect_device() with CUDA/MPS/CPU detection and validation
- convert_pdf_with_fallback: 69 lines with try/except, fallback logic, OOM recovery, strict_gpu enforcement
- check_gpu_availability: 27 lines with torch import, CUDA check, MPS check with multiple conditions, actionable messages
- Pipeline integration: Calls convert_pdf_with_fallback, unpacks response, logs fallback, updates results
- CLI: Argparse definition, config propagation, verbose display with Rich console
- Tests: 5 comprehensive tests for convert_pdf_with_fallback (exists, fallback, strict_gpu, success, return type)

**Level 3: Wired** — All connections verified
- pipeline.py imports surya module, calls convert_pdf_with_fallback (line 428)
- convert_pdf_with_fallback calls load_models for CPU retry (line 213)
- load_models imports and uses detect_device (lines 76-80)
- CLI imports check_gpu_availability and displays in verbose mode (lines 316-319)
- strict_gpu propagates from CLI args to PipelineConfig to convert_pdf_with_fallback
- Fallback results tracked in FileResult.device_used and phase_timings["surya_fallback"]

### Wiring Patterns Verified

**Pattern: GPU Attempt → CPU Fallback**
- surya.py:184 attempts convert_pdf() with GPU model_dict
- surya.py:186-194 catches RuntimeError, checks strict_gpu
- surya.py:197-215 (OUTSIDE except) clears GPU memory, loads CPU models, retries
- Returns (markdown, True) to signal fallback occurred

**Pattern: Device Detection → Model Loading**
- surya.py:76-80 calls detect_device() when device arg is None
- detect_device() validates CUDA/MPS with test tensor (device.py:50-66)
- Returns DeviceInfo with validated device_type
- Model loading proceeds with validated device string

**Pattern: Fallback → Result Tracking**
- pipeline.py:442-449 checks fallback_occurred flag
- Logs warning with filename
- Updates file_result.device_used to "cpu"
- Sets phase_timings["surya_fallback"] = True for transparency

**Pattern: Startup Validation → User Feedback**
- environment.py:154-155 calls check_gpu_availability in log_startup_diagnostics
- Logs via logger.info for batch processing
- cli.py:316-319 calls check_gpu_availability in verbose mode
- Displays via Rich console for interactive use

### Implementation Quality

**Strengths:**
1. **OOM Recovery Pattern**: GPU memory cleared OUTSIDE except block (lines 197-207) to allow proper garbage collection — critical for MPS memory management
2. **Actionable Messages**: check_gpu_availability returns specific reasons ("MPS built but not available (macOS < 12.3 or no GPU)") not just bool
3. **Lazy Imports**: Torch imported inside functions to avoid loading ML dependencies at module import time
4. **Transparency**: Fallback tracked in results for observability, not silent
5. **Test Coverage**: 5 tests for convert_pdf_with_fallback using mocks, verifying all paths
6. **Device Validation**: detect_device() validates with test tensor allocation, not just capability check

**Deviations from Standard Patterns:**
- DEV-04 implemented via full-CPU fallback rather than per-model device split
- Rationale: Marker API currently uses unified device per model_dict
- Detection/recognition split deferred pending Marker API changes
- Documented in 12-05 SUMMARY as intentional design decision

**Design Consistency:**
- Follows existing lazy import pattern (torch, marker imports inside functions)
- Uses dataclass pattern for DeviceInfo (consistent with SuryaConfig, PipelineConfig)
- Logging via module logger (consistent with rest of codebase)
- CLI flag propagation via PipelineConfig (consistent with force_tesseract, force_surya)

## Gaps Summary

**No gaps found.** All must-haves verified at all three levels (exists, substantive, wired).

**Human verification required** for 4 behavioral tests:
1. MPS device selection on Apple Silicon hardware
2. Actual GPU fallback triggering
3. Strict GPU mode enforcement
4. Cross-platform startup diagnostics

These cannot be verified programmatically without Apple Silicon hardware and actual model loading.

---

_Verified: 2026-02-04T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
