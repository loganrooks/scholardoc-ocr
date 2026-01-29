# Phase 2: Quality Analysis Enhancement - Context

**Gathered:** 2026-01-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace regex-only quality detection with multi-signal composite scoring that integrates OCR confidence, dictionary validation, garbled text regex, and layout checks. Add German language support. Per-page quality breakdown available in pipeline results. This phase does NOT change OCR backends or pipeline orchestration — it only enhances how quality is measured.

</domain>

<decisions>
## Implementation Decisions

### Signal weighting
- Claude's discretion on combining strategy (weighted average vs worst-signal-wins)
- Short-circuit on clear cases: if confidence is very high or very low, skip remaining signals for speed
- Composite score is a single 0-1 float for threshold comparison, with per-signal breakdown available in results
- Dictionary uses a bundled word list (no external spellcheck dependency)
- Word list must be extensible: built-in list + user-supplied custom vocabulary file + automatic "likely real word" heuristic
- Automatic heuristic detects words flagged as unknown but structurally valid (e.g. regular occurrence across pages) — Claude decides whether within-run or persisted
- Dictionary signal distinguishes "unknown but structured word" (penalize less) from "garbled nonsense" (penalize heavily)

### Threshold behavior
- Composite threshold plus per-signal floor values (e.g. confidence can't be below a minimum even if composite is above threshold)
- Per-signal floors start as hardcoded defaults, exposed via library API for calibration — CLI users see only the composite threshold
- Gray zone around threshold triggers additional analysis on borderline pages — Claude decides the extra check strategy
- Default threshold value to be recalibrated after implementation (not locked to 0.85)
- Results expose per-signal breakdown: which signals passed/failed and their individual scores
- Include text snippets that triggered low scores — the actual problematic text plus surrounding context for debugging
- Claude decides whether snippets go in structured results only or also to an optional debug file
- Gray zone triggers reported via callbacks (logged, visible in progress)

### German language integration
- German is opt-in via language configuration, not enabled by default
- Philosophy-focused German vocabulary (Heidegger, Husserl, Kant terminology) as baseline
- Must handle mixed-language pages (English text with inline German quotations) — Claude decides approach (multi-language dictionary vs per-block detection)
- Claude's discretion on: vocabulary curation method, Tesseract lang flag strategy, compound word handling, per-language vs flat custom word lists

### hOCR confidence usage
- Claude's discretion on: hOCR availability fallback, page-level aggregation strategy, word-length weighting, outlier filtering, bounding box extraction, parsed data retention
- Must handle mix of simple and complex layouts (single-column, multi-column, footnotes, marginal notes)

### Claude's Discretion
- Signal combination algorithm (weighted average, worst-signal-wins, or hybrid)
- hOCR parsing strategy and what to extract beyond confidence
- Confidence aggregation method (simple average vs cluster-aware)
- Gray zone extra analysis approach
- Auto-detected vocabulary persistence (within-run vs across-run)
- German compound word handling
- Tesseract language flag strategy when German is enabled
- Debug output format (structured results only vs optional file)
- Word-length weighting for confidence signal
- Outlier filtering for noisy Tesseract confidence values

</decisions>

<specifics>
## Specific Ideas

- User wants the word list to "accommodate words we didn't consider" — the auto-detection heuristic should catch recurring valid words that aren't in any dictionary
- Text snippets of problematic triggering text and surroundings should be extractable for debugging/tuning
- The system handles a mix of simple and complex academic layouts (single-column, multi-column, footnotes, marginal notes)
- German quotations appear inline within English academic text — quality analysis must not penalize these

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-quality-analysis-enhancement*
*Context gathered: 2026-01-29*
