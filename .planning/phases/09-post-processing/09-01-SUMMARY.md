---
phase: 09-post-processing
plan: 01
subsystem: text-processing
tags: [unicode, dehyphenation, paragraph-joining, punctuation, NFC]
requires: [08-robustness]
provides: [postprocess-module, text-transforms]
affects: [09-02-pipeline-integration]
tech-stack:
  added: []
  patterns: [transform-pipeline, regex-based-text-cleanup]
key-files:
  created:
    - src/scholardoc_ocr/postprocess.py
    - tests/test_postprocess.py
  modified: []
key-decisions:
  - id: POST-ORDER
    decision: "dehyphenate runs before join_paragraphs in pipeline (needs newlines for pattern matching)"
    reason: "Hyphen-newline pattern destroyed if paragraphs joined first"
duration: ~4min
completed: 2026-02-03
---

# Phase 9 Plan 01: Text Transforms Summary

**NFC normalization, ligature decomposition, paragraph joining, dehyphenation, and punctuation cleanup via TDD.**

## Performance

- RED phase: 22 failing tests written and committed
- GREEN phase: All 22 tests passing, lint clean

## Accomplishments

- Created `postprocess.py` with 5 exported functions covering POST-01 through POST-07
- `normalize_unicode`: NFC normalization, 5 ligature decompositions, soft hyphen removal
- `join_paragraphs`: Single newline joining with heading and indent detection
- `dehyphenate`: Line-break hyphen rejoining with proper name preservation (capitalization heuristic + known names set)
- `normalize_punctuation`: Punctuation spacing and whitespace collapse
- `postprocess`: Chained pipeline function

## Task Commits

| Task | Name | Commit | Type |
|------|------|--------|------|
| 1 | RED -- Write failing tests | 2b939d1 | test |
| 2 | GREEN -- Implement all transforms | e88e188 | feat |

## Decisions Made

| ID | Decision | Reason |
|----|----------|--------|
| POST-ORDER | dehyphenate before join_paragraphs | Hyphen-newline pattern needs raw newlines |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pipeline ordering**
- **Found during:** Task 2 (GREEN)
- **Issue:** Plan specified order unicode -> paragraphs -> dehyphenate -> punctuation, but join_paragraphs destroys the `hyphen-\n` pattern before dehyphenate can match
- **Fix:** Reordered to unicode -> dehyphenate -> paragraphs -> punctuation
- **Files modified:** src/scholardoc_ocr/postprocess.py

**2. [Rule 1 - Bug] Fixed ligature test expectation**
- **Found during:** Task 2 (GREEN)
- **Issue:** Test expected "fffiflffiffle" but correct decomposition of all 5 ligatures concatenated is "fffiflffiffl"
- **Fix:** Corrected test assertion
- **Files modified:** tests/test_postprocess.py

## Issues Encountered

None beyond the deviations above.

## Next Phase Readiness

- postprocess module ready for integration into pipeline (09-02)
- All exports available: `postprocess`, `normalize_unicode`, `join_paragraphs`, `dehyphenate`, `normalize_punctuation`
