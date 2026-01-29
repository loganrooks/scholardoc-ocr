---
phase: 02
plan: 01
subsystem: quality-analysis
tags: [dictionary, wordlist, german, quality-signal]
requires: [01-foundation]
provides: [dictionary-signal, german-vocabulary, signal-result-type]
affects: [02-02, 02-03, 02-04]
tech-stack:
  added: []
  patterns: [signal-module-pattern, bundled-data-resources]
key-files:
  created:
    - src/scholardoc_ocr/dictionary.py
    - src/scholardoc_ocr/data/wordlist.txt
  modified:
    - src/scholardoc_ocr/types.py
    - src/scholardoc_ocr/quality.py
key-decisions:
  - id: dict-scoring
    decision: "Weighted scoring: known=1.0, unknown_structured=0.5, unknown_garbled=0.0"
    rationale: "Penalizes garbled text heavily while being lenient on valid words not in dictionary"
  - id: german-suffix-skip
    decision: "Words ending with German suffixes skip consonant_cluster pattern check"
    rationale: "German compound words naturally have long consonant clusters that trigger false positives"
duration: ~3m
completed: 2026-01-29
---

# Phase 2 Plan 1: Dictionary Signal and German Vocabulary Summary

Dictionary-based quality signal scoring text via 18K-word bundled list with three-tier classification (known/structured/garbled), plus German philosophical vocabulary in quality analyzer whitelist with suffix-aware consonant cluster suppression.

## Performance

- Duration: ~3 minutes
- Tasks: 2/2 complete
- No blockers encountered

## Accomplishments

1. Created `SignalResult` dataclass in types.py as shared return type for all signal modules
2. Built `DictionarySignal` class that loads bundled wordlist and classifies words into known, unknown-structured, and unknown-garbled categories
3. Generated 18,316-word bundled word list covering English, French, German, Latin, and Greek academic vocabulary
4. Expanded `VALID_TERMS` from ~40 to 163 terms with organized sub-sets (Kant, Hegel, Husserl, Heidegger, French, Greek)
5. Added German suffix awareness (-keit, -heit, -ung, -schaft, -lich, -isch, -tum, -nis) to suppress consonant_cluster false positives

## Task Commits

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Dictionary signal module and bundled word list | 7813599 | types.py, dictionary.py, wordlist.txt |
| 2 | German philosophical vocabulary in quality.py | ec6ec2d | quality.py |

## Files Changed

- `src/scholardoc_ocr/types.py` -- Added `SignalResult` dataclass
- `src/scholardoc_ocr/dictionary.py` -- New `DictionarySignal` class with `score()` method
- `src/scholardoc_ocr/data/wordlist.txt` -- 18,316-word bundled word list
- `src/scholardoc_ocr/quality.py` -- Expanded `VALID_TERMS` (163 terms), added `GERMAN_SUFFIXES`, German suffix-aware pattern checking

## Decisions Made

1. **Three-tier word classification**: known (1.0), unknown-structured (0.5), unknown-garbled (0.0) provides nuanced scoring that doesn't penalize valid non-dictionary words as harshly as actual garbled text
2. **Structural validity via vowel ratio, repetition, and unique-char ratio**: Simple heuristics that effectively distinguish real words from OCR artifacts without needing a full language model
3. **German suffix-based consonant cluster suppression**: Rather than raising the consonant cluster threshold further, specifically exempt words with known German suffixes

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Found

None.

## Next Phase Readiness

- `SignalResult` type is ready for use by confidence extraction (02-02) and other signal modules
- `DictionarySignal` pattern established for other signal modules to follow
- German vocabulary coverage enables processing of German philosophical texts without false positives
