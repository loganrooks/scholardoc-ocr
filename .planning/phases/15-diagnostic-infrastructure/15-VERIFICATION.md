---
phase: 15-diagnostic-infrastructure
verified: 2026-02-17T22:58:48Z
status: passed
score: 12/12 must-haves verified
---

# Phase 15: Diagnostic Infrastructure Verification Report

**Phase Goal:** Users can run OCR with --diagnostics and get rich per-page diagnostic data revealing why each page scored the way it did
**Verified:** 2026-02-17T22:58:48Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | PageDiagnostics dataclass exists with all fields for always-captured and diagnostics-gated data | VERIFIED | diagnostics.py lines 59-112: all fields present including signal_scores, signal_details, composite_weights, signal_disagreements, has_signal_disagreement, postprocess_counts, struggle_categories, image_quality, tesseract_text, engine_diff |
| 2 | SignalDisagreement and EngineDiff dataclasses exist for structured sub-data | VERIFIED | diagnostics.py lines 32-56: both dataclasses with to_dict() on EngineDiff |
| 3 | PageResult has an optional diagnostics field that defaults to None | VERIFIED | types.py line 91: `diagnostics: PageDiagnostics | None = None`; backward compat confirmed live |
| 4 | Existing code constructing PageResult continues to work without changes | VERIFIED | Live test: `PageResult(page_number=0, ...)` without diagnostics creates successfully, to_dict() excludes diagnostics key |
| 5 | All diagnostic dataclasses pickle successfully through ProcessPoolExecutor | VERIFIED | Live pickle roundtrip: 417 bytes, full roundtrip confirmed |
| 6 | Every PageResult from _tesseract_worker carries a PageDiagnostics with signal_scores, signal_details, composite_weights, signal_disagreements, has_signal_disagreement, and struggle_categories populated | VERIFIED | pipeline.py lines 111-137 and 214-245: build_always_diagnostics called in both code paths (existing-text-is-good and Tesseract-processed), wrapped in try/except |
| 7 | Post-processing counters (dehyphenations, paragraph_joins, unicode_normalizations, punctuation_fixes) are tracked and attached to diagnostics | VERIFIED | postprocess.py: all 4 functions accept optional counts parameter; live test shows {'unicode_normalizations': 0, 'dehyphenations': 1, 'paragraph_joins': 0, 'punctuation_fixes': 1} for test input; pipeline.py attaches pp_counts to each page's diagnostics |
| 8 | User can run `ocr --diagnostics file.pdf` and get per-page image quality metrics (DPI, contrast, blur_score, skew_angle) | VERIFIED | cli.py lines 255-260: --diagnostics flag present in argparser; diagnostics.py lines 319-377: analyze_image_quality() computes DPI, contrast, blur_score, skew_angle; pipeline.py wires it in both _tesseract_worker paths gated on config_dict.get("diagnostics", False) |
| 9 | For pages processed by both engines, Tesseract text is preserved before Surya overwrites it, and a structured word-level diff is computed | VERIFIED | pipeline.py lines 578-621: DIAG-04 preservation block executes BEFORE map_results_to_files(), diff computed AFTER; timing is correct |
| 10 | A JSON sidecar file `{stem}.diagnostics.json` is written alongside the output PDF containing full per-page diagnostic data | VERIFIED | pipeline.py lines 754-799: sidecar written to final_dir with version="1.0", filename, generated_at, pipeline_config, and per-page data including page.diagnostics.to_dict() |
| 11 | Running without --diagnostics produces the same output as before (no image analysis, no text preservation, no sidecar) | VERIFIED | All diagnostic operations gated behind config.diagnostics / config_dict.get("diagnostics", False); sidecar block in `if config.diagnostics:` guard |
| 12 | CLI --diagnostics flag propagates through PipelineConfig to pipeline behavior | VERIFIED | cli.py line 373: `diagnostics=args.diagnostics`; pipeline.py line 54: `diagnostics: bool = False` in PipelineConfig; config_dict line 367: `"diagnostics": config.diagnostics` |

**Score:** 12/12 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/scholardoc_ocr/diagnostics.py` | PageDiagnostics, SignalDisagreement, EngineDiff dataclasses + 4 utility functions + analyze_image_quality | VERIFIED | 419 lines; all 8 symbols exported and importable; all 4 utility functions implemented with real logic |
| `src/scholardoc_ocr/types.py` | PageResult with `diagnostics: PageDiagnostics \| None = None` field | VERIFIED | Line 91 confirms field; to_dict() conditionally includes diagnostics at lines 104-105 |
| `src/scholardoc_ocr/postprocess.py` | Postprocess functions with optional counter tracking | VERIFIED | All 5 functions (normalize_unicode, dehyphenate, join_paragraphs, normalize_punctuation, postprocess) accept optional counts parameter; live test confirms counting and backward compat |
| `src/scholardoc_ocr/pipeline.py` | Pipeline wiring of always-captured diagnostics + gated features + sidecar | VERIFIED | build_always_diagnostics in both _tesseract_worker paths; diagnostics field in PipelineConfig; config_dict carries diagnostics; DIAG-04 text preservation and diff; DIAG-08 sidecar |
| `src/scholardoc_ocr/cli.py` | --diagnostics CLI flag | VERIFIED | Lines 255-260: argparser flag; line 373: propagated to PipelineConfig |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| types.py | diagnostics.py | `from .diagnostics import PageDiagnostics` under TYPE_CHECKING | WIRED | types.py lines 10-11: TYPE_CHECKING guard present |
| pipeline.py | diagnostics.py | `build_always_diagnostics` call in _tesseract_worker | WIRED | pipeline.py lines 63 (import), 116 and 223 (calls in both code paths) |
| pipeline.py | diagnostics.py | `analyze_image_quality` when diagnostics enabled | WIRED | pipeline.py lines 122-124 and 230-232: lazy import + call gated on config_dict.get("diagnostics", False) |
| pipeline.py | diagnostics.py | `compute_engine_diff` for Surya-processed pages | WIRED | pipeline.py lines 601-617: import + call after map_results_to_files() |
| pipeline.py | diagnostics.py | `classify_struggle` for Surya reclassification | WIRED | pipeline.py lines 647-664: import + call to update struggle_categories |
| pipeline.py | postprocess.py | `counts=` parameter to postprocess function | WIRED | pipeline.py lines 102-104 and 205-207: postprocess called with counts dict; diag.postprocess_counts set from result |
| cli.py | pipeline.py | `diagnostics=True` in PipelineConfig | WIRED | cli.py line 373: `diagnostics=args.diagnostics`; pipeline.py line 367 in config_dict |

### Requirements Coverage

All 8 DIAG requirements from Phase 15 planning are satisfied:

| Requirement | Status | Evidence |
|-------------|--------|---------|
| DIAG-01: Image quality metrics (DPI, contrast, blur, skew) | SATISFIED | diagnostics.py analyze_image_quality(); wired in both _tesseract_worker paths |
| DIAG-02: Signal breakdown (scores, details, weights) | SATISFIED | build_always_diagnostics() extracts from QualityResult; attached to every PageResult |
| DIAG-03: Signal disagreement detection with magnitude + has_signal_disagreement | SATISFIED | compute_signal_disagreements() in diagnostics.py; has_disagreement flag set at DISAGREEMENT_THRESHOLD=0.3 |
| DIAG-04: Tesseract text preservation + word-level engine diff | SATISFIED | pipeline.py: preservation BEFORE map_results_to_files(), diff AFTER; timing is correct |
| DIAG-05: Postprocess change counts | SATISFIED | postprocess.py: 4 counters tracked; pipeline attaches pp_counts to each page |
| DIAG-06: Struggle category labels (8 independent rules) | SATISFIED | classify_struggle() in diagnostics.py with all 8 rules; Surya-processed pages reclassified |
| DIAG-07: PageResult.diagnostics optional field | SATISFIED | types.py line 91; backward-compatible default None |
| DIAG-08: JSON diagnostic sidecar output | SATISFIED | pipeline.py lines 754-799: {stem}.diagnostics.json written to final_dir |

### Anti-Patterns Found

No TODO, FIXME, XXX, HACK, or PLACEHOLDER comments in any Phase 15 source files. No empty implementations or stub returns found.

One known limitation documented in planning and code comments: postprocess counts are global (applied to all-pages-joined text), then the same counts dict is attached to each individual page's diagnostics. This is an intentional approximation per Phase 15 SUMMARY.md ("Phase 19 will refine to per-page counting"). This is a warning-level item that does not block the phase goal.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| pipeline.py | 118 | `diag.postprocess_counts = dict(pp_counts)` applied identically to all pages | Warning | Postprocess counts reflect whole-document totals per page, not per-page actuals. Deferred to Phase 19. Does not prevent goal: data is present and accurate at document level. |

### Test Suite Status

Pre-existing failures (not caused by Phase 15, confirmed by checking pre-Phase-15 git state):
- `tests/test_callbacks.py` -- imports `ExtendedResult` from pipeline which never existed; collection error predates Phase 15
- `tests/test_surya.py::TestLoadModels::test_success` and `test_with_device` -- assert `load_models()` returns dict; actual function returns `(dict, device)` tuple; mismatch predates Phase 15

All other tests: **263 passed, 2 skipped** (ignoring pre-existing failures and benchmarks). No regressions introduced by Phase 15.

### Human Verification Required

The following items need a real PDF to verify end-to-end behavior:

**1. JSON Sidecar Content Verification**

Test: Run `ocr --diagnostics path/to/test.pdf -o /tmp/diag_test` then inspect `/tmp/diag_test/final/*.diagnostics.json`

Expected: File contains version="1.0", per-page entries with signal_scores, struggle_categories, and (if applicable) image_quality metrics

Why human: Requires a real PDF and real Tesseract installation to exercise the full pipeline path

**2. Image Quality Metrics Validity**

Test: Run with --diagnostics on a real scanned PDF and inspect `image_quality` fields in sidecar

Expected: dpi (float or null), contrast (0-0.3 range), blur_score (positive float, lower=blurrier), skew_angle (degrees near 0 for straight pages)

Why human: cv2/numpy image processing requires a real page render; cannot verify metric correctness without actual image data

**3. Engine Diff on Dual-Engine Pages**

Test: Run with `--diagnostics --quality 1.0` to force Surya on all pages; inspect `engine_diff` in sidecar

Expected: additions, deletions, substitutions as word-level lists showing what Surya changed vs Tesseract

Why human: Requires both Tesseract and Surya to process the same page

### Gaps Summary

No gaps. All phase must-haves are verified. The phase goal is achieved: users can run `ocr --diagnostics` and receive rich per-page diagnostic data in a `{stem}.diagnostics.json` sidecar file, with signal score breakdowns, struggle categories, postprocess counters, and (when applicable) image quality metrics and engine diffs.

---

_Verified: 2026-02-17T22:58:48Z_
_Verifier: Claude (gsd-verifier)_
