# Phase 16: Test Corpus & Ground Truth - Context

**Gathered:** 2026-02-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a curated evaluation corpus of philosophy PDFs with ground truth text, enabling repeatable quality measurement in Phases 17-19. The corpus provides aligned pairs of (OCR output, ground truth) with enough failure-mode coverage for statistical analysis.

Requirements: CORP-01 through CORP-04 (with sequencing revision — see below).

**Sequencing revision:** The roadmap called Phases 15 and 16 "parallelizable," but Phase 16's design genuinely benefits from Phase 15's output. Diagnostic data (struggle categories, signal scores, gray-zone flags) drives page selection and replaces manual challenge profiling. CORP-04 (baseline run) must happen before CORP-03 (ground truth creation), because diagnostic output informs which pages get ground truth.

</domain>

<decisions>
## Implementation Decisions

### Page selection strategy (coverage-based, not count-based)

The spec says "10-20 selected pages per document" — that's count-based. Downstream (Phase 19 correlation analysis) needs data points per failure mode, not per document. 20 easy pages are worth less than 5 pages spanning different struggle categories.

- Selection driven by Phase 15 diagnostic data: struggle categories, gray-zone flags, signal disagreement
- Two categories of ground truth pages:
  - **Difficult pages (~40-50):** Selected via diagnostic coverage matrix — at least 2-3 pages per detected struggle category, all gray-zone pages, all signal-disagreement pages
  - **Regression pages (Claude determines count after seeing baseline):** ToC, front matter, clean body text — pages that should always work correctly
- Variable count per document — distribution driven by where interesting pages actually are, not arithmetic
- Total target: ~60-70 pages, but coverage drives the number

### Ground truth creation (Opus vision transcription + spot-check)

- Render selected pages as images (PyMuPDF, same as Phase 15 image quality analysis)
- Claude Opus transcribes from page images — handles philosophical vocabulary and context well
- Human spot-checks ~10-15% sample for quality assurance
- If spot-check reveals systematic patterns (consistent ligature errors, diacritics issues), add a targeted correction pass

### Ground truth fidelity (dual-layer: raw + normalized-at-comparison)

- **Stored ground truth (canonical):** Faithful transcription of what's on the page
  - Proper Unicode, paragraph structure preserved (blank lines between paragraphs)
  - Footnotes separated from body text
  - Greek/Latin characters preserved with correct Unicode
  - Diacritics preserved
  - **Excluded:** page numbers, running headers, marginal annotations
- **Comparison normalization (Phase 18 responsibility):** Both OCR output and ground truth run through the same normalization pipeline before CER/WER computation
  - This separates "OCR accuracy" from "normalization disagreement"
  - Phase 19 can distinguish real OCR errors from postprocessing differences
- One ground truth file per page, named by document ID + page number

### Manifest design (observable metadata, not pre-labeled challenges)

Per Phase 15's lesson: don't pre-label "challenge profiles" before ground truth exists. Phase 19 discovers actual challenges empirically.

- `corpus.json` manifest with per-document entries:
  - Observable facts: `title`, `author`, `language`, `page_count`, `scan_source`
  - Structural booleans: `has_footnotes`, `has_greek`, `has_toc`
  - Diagnostic summary (generated from baseline, not hand-labeled): dominant struggle categories, percentage of flagged pages, signal score ranges
- Per-page ground truth mapping within each document entry
- PDF symlinks gitignored; manifest and ground truth committed

### Baseline as workflow input (not just reference snapshot)

- Baseline = full pipeline run with `--diagnostics` on each corpus document
- Store BOTH diagnostic sidecar AND OCR output text:
  - **Diagnostic sidecar** → Phase 17 smart page selection (EVAL-04), Phase 19 score distributions
  - **OCR output text** → Phase 18 CER/WER comparison target
- Storage: `tests/corpus/baselines/{document-id}/` with `.diagnostics.json` and output text
- Pin pipeline version + Tesseract/Surya versions in manifest for reproducibility
- After Phase 20 improvements, re-running produces an "after" baseline for comparison

### Revised requirement sequencing

Original order assumed parallelism with Phase 15. Revised order uses Phase 15's output:

1. **CORP-01:** Create corpus infrastructure (directory structure, manifest skeleton)
2. **CORP-02:** Register 4 documents (symlinks, manifest entries with observable metadata)
3. **CORP-04:** Run baseline with `--diagnostics` (produces diagnostic data + OCR output)
4. **Page selection:** Build coverage matrix from diagnostic output
5. **CORP-03:** Opus transcription of selected pages → ground truth files + manifest mapping
6. Update manifest with diagnostic summary from baseline

### Corpus extensibility

- Adding a document = manifest entry + PDF symlink + baseline run + ground truth files
- No structural changes needed
- If Phase 19 reveals coverage gaps (e.g., need `bad_scan` examples), adding a 5th document is trivial

### Claude's Discretion
- Exact coverage matrix thresholds (how many pages per struggle category)
- Regression set size and composition (determined after seeing baseline diagnostic output)
- Ground truth file format conventions (encoding, line endings, paragraph marking)
- Manifest JSON schema structure (field names, nesting)
- Directory layout within `tests/corpus/`
- How to handle pages with complex layout (tables, equations, multi-column)

</decisions>

<specifics>
## Specific Ideas

- Phase 15's lesson applies: "stop guessing, start measuring." Don't pre-label challenge profiles — let diagnostic data and Phase 19 analysis reveal the actual challenges.
- The sequencing change (CORP-04 before CORP-03) is the same kind of insight as Phase 15's two-tier diagnostic gating: the data you already have should inform what you do next.
- Opus vision transcription makes 60-70 pages of ground truth feasible without days of manual work.
- The dual-layer ground truth design (raw storage, normalize at comparison time) prevents baking normalization assumptions into the corpus — same philosophy as Phase 15 storing raw disagreement magnitudes rather than pre-thresholded booleans.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

## Open Questions

| Question | Why It Matters | Criticality | Status |
|----------|----------------|-------------|--------|
| Do the 4 named PDFs cover enough struggle categories? | If all 4 are similar quality scans, we may lack `bad_scan` or other category coverage | Medium | Pending — baseline diagnostic run will reveal |
| How accurate is Opus vision transcription on degraded scans? | If scan quality is poor, Opus may also struggle, producing unreliable ground truth | Medium | Pending — spot-check will validate |
| Are Tesseract/Surya versions pinned in the development environment? | Baseline reproducibility requires version pinning | Low | Pending — researcher can check |

---

*Phase: 16-test-corpus-ground-truth*
*Context gathered: 2026-02-17*
