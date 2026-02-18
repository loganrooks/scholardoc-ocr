# Roadmap: scholardoc-ocr

## Milestones

- v1.0 MVP - Phases 1-7 (shipped 2026-02-02)
- v2.0 Post-Processing + Robustness - Phases 8-10 (shipped 2026-02-02)
- v2.1 Performance - Phases 11-14 (shipped 2026-02-04)
- v3.0 Diagnostic Intelligence - Phases 15-20 (in progress)

## Phases

<details>
<summary>v1.0 MVP (Phases 1-7) - SHIPPED 2026-02-02</summary>

See .planning/milestones/v1.0-ROADMAP.md for v1.0 details. 7 phases, 17 plans, 30 requirements delivered.

</details>

<details>
<summary>v2.0 Post-Processing + Robustness (Phases 8-10) - SHIPPED 2026-02-02</summary>

See .planning/milestones/v2.0-ROADMAP.md for v2.0 details. 3 phases, 8 plans, 20 requirements delivered.

</details>

<details>
<summary>v2.1 Performance (Phases 11-14) - SHIPPED 2026-02-04</summary>

See .planning/milestones/v2.1-ROADMAP.md for v2.1 details. 4 phases, 17 plans, 22 requirements delivered.

</details>

### v3.0 Diagnostic Intelligence (In Progress)

**Milestone Goal:** Instrument the pipeline to understand where and why OCR fails, build an LLM evaluation framework with ground truth corpus, analyze quality scoring empirically, then apply targeted improvements based on data rather than speculation.

- [x] **Phase 15: Diagnostic Infrastructure** - Instrument pipeline to capture per-page diagnostic data (completed 2026-02-17)
- [ ] **Phase 16: Test Corpus & Ground Truth** - Build evaluation corpus with reference text for philosophy PDFs
- [ ] **Phase 17: Evaluation Framework** - LLM-as-judge evaluation via CLI with versioned templates
- [ ] **Phase 18: Quality Metrics & Result Storage** - CER/WER computation against ground truth with structured result storage
- [ ] **Phase 19: Analysis & Calibration** - Statistical analysis of quality scoring against ground truth
- [ ] **Phase 20: Targeted Improvements** - Data-driven quality improvements based on analysis findings

## Phase Details

### Phase 15: Diagnostic Infrastructure
**Goal**: Users can run OCR with --diagnostics and get rich per-page diagnostic data revealing why each page scored the way it did
**Depends on**: Nothing (foundation phase, parallelizable with Phase 16)
**Requirements**: DIAG-01, DIAG-02, DIAG-03, DIAG-04, DIAG-05, DIAG-06, DIAG-07, DIAG-08
**Success Criteria** (what must be TRUE):
  1. User runs `ocr --diagnostics file.pdf` and the JSON sidecar contains per-page image quality metrics (DPI, contrast, blur score, skew angle) alongside OCR results
  2. User can see why a page was flagged: the diagnostic output shows individual signal scores (garbled, dictionary, confidence) and the composite weights used, not just the final composite score
  3. User can identify pages where quality signals disagree (e.g., high confidence but high garbled score) via explicit signal disagreement flags in the diagnostic output
  4. For pages processed by both engines, user can see what Surya changed: a structured diff (additions, deletions, substitutions) between Tesseract and Surya text is preserved in diagnostics
  5. Each page in the diagnostic output carries a struggle category label (bad_scan, character_confusion, vocabulary_miss, layout_error, language_confusion, signal_disagreement, gray_zone, surya_insufficient) explaining the dominant failure mode
**Plans:** 3 plans
Plans:
- [x] 15-01-PLAN.md -- Diagnostic data model: dataclasses, utility functions, PageResult integration
- [x] 15-02-PLAN.md -- Always-captured diagnostics: pipeline wiring, postprocess counters
- [x] 15-03-PLAN.md -- Diagnostics-gated features: image quality, engine diff, CLI flag, JSON sidecar

### Phase 16: Test Corpus & Ground Truth
**Goal**: A curated test corpus of difficult philosophy PDFs exists with human-verified ground truth text, enabling repeatable evaluation
**Depends on**: Nothing (foundation phase, parallelizable with Phase 15)
**Requirements**: CORP-01, CORP-02, CORP-03, CORP-04
**Success Criteria** (what must be TRUE):
  1. tests/corpus/ directory exists with a corpus.json manifest describing each document (title, author, language, challenge profile) and PDF symlinks are gitignored while manifest and ground truth are committed
  2. Ground truth text files exist for 10-20 selected pages per corpus document (4 philosophy PDFs: Simondon, Derrida x3), stored in tests/corpus/ground_truth/ with page-to-file mapping in the manifest
  3. A diagnostic baseline run has been captured for all corpus documents with full diagnostic output stored in tests/corpus/baselines/, establishing the starting point for evaluation
**Plans:** 3 plans
Plans:
- [ ] 16-01-PLAN.md -- Corpus infrastructure: directory structure, manifest, helper scripts
- [ ] 16-02-PLAN.md -- Baseline capture and coverage-based page selection
- [ ] 16-03-PLAN.md -- Ground truth creation via Opus transcription and manifest finalization

### Phase 17: Evaluation Framework
**Goal**: Users can evaluate OCR quality using LLM-as-judge (claude/codex CLI) with versioned templates, smart page selection, and structured output
**Depends on**: Phase 15 (diagnostic data for smart page selection), Phase 16 (corpus for evaluation targets)
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-07, EVAL-08
**Success Criteria** (what must be TRUE):
  1. User runs `ocr evaluate` on existing OCR output and gets structured evaluation results from claude or codex CLI without re-running the pipeline
  2. Evaluation uses versioned prompt templates loaded from eval/templates/ files (not embedded strings), each template has a content-addressable ID, and changing a template produces a new version tracked in git
  3. Smart page selection automatically generates an evaluation manifest from diagnostic data: all flagged pages, gray zone pages (threshold +/-0.05), signal disagreement pages, plus a stratified control sample -- user does not manually pick pages
  4. Running the same template through both claude and codex evaluators produces comparable structured results, with automatic disagreement flagging where evaluators differ
**Plans**: TBD

### Phase 18: Quality Metrics & Result Storage
**Goal**: Quantitative OCR accuracy metrics (CER/WER) computed against ground truth, with structured result storage enabling cross-run comparison
**Depends on**: Phase 16 (ground truth text), Phase 17 (evaluation runner infrastructure)
**Requirements**: EVAL-05, EVAL-06
**Success Criteria** (what must be TRUE):
  1. User can compute CER, WER, and MER metrics for any OCR output page against its ground truth text, with results reported per page and aggregated per document
  2. All evaluation results (both LLM judgments and quantitative metrics) are stored as structured JSON with schema version, template version, evaluator identity, and timestamp -- enabling comparison across evaluation runs over time
**Plans**: TBD

### Phase 19: Analysis & Calibration
**Goal**: Statistical analysis reveals how well quality scoring predicts actual OCR accuracy, with actionable recommendations for threshold and weight adjustments
**Depends on**: Phase 18 (CER/WER metrics as ground truth signal)
**Requirements**: ANLZ-01, ANLZ-02, ANLZ-03, ANLZ-04, ANLZ-05
**Success Criteria** (what must be TRUE):
  1. User can see score distribution analysis showing how garbled, dictionary, confidence, and composite scores distribute across corpus documents -- revealing whether scores cluster, bimodal split, or spread evenly
  2. User can see threshold sensitivity analysis showing what happens at each threshold value (0.70-0.95 in 0.05 steps): how many pages get flagged for Surya, and how that correlates with actual quality
  3. User can see which quality signals actually predict OCR accuracy: Pearson/Spearman correlation between each signal and ground truth CER/WER, identifying which signals carry weight and which are noise
  4. User can see false positive and false negative pages: pages scored as good but actually bad (missed by quality scoring), and pages scored as bad but actually good (wasted Surya processing)
  5. A human-readable analysis report exists with specific recommendations for threshold value, signal weights, and signal floor adjustments -- recommendations only, not automated changes
**Plans**: TBD

### Phase 20: Targeted Improvements
**Goal**: Measurable quality improvements applied to pipeline based on analysis findings, validated by re-evaluation on corpus
**Depends on**: Phase 19 (analysis findings drive what to improve)
**Requirements**: IMPR-01, IMPR-02, IMPR-03, IMPR-04
**Success Criteria** (what must be TRUE):
  1. Quality threshold and signal weights in quality.py have been adjusted based on Phase 19 analysis, with a before/after evaluation comparison demonstrating the impact of each change
  2. Dictionary whitelist has been expanded based on false positive analysis -- legitimate academic terms that were being flagged as garbled are no longer penalized
  3. Re-evaluation on corpus documents after all improvements demonstrates measurable quality gain (lower CER/WER or better flagging accuracy) compared to the Phase 16 diagnostic baseline
**Plans**: TBD

## Progress

**Execution Order:**
Phases 15 and 16 are parallelizable foundations. After both complete: 17 -> 18 -> 19 -> 20.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-7 | v1.0 | 17/17 | Complete | 2026-02-02 |
| 8-10 | v2.0 | 8/8 | Complete | 2026-02-02 |
| 11-14 | v2.1 | 17/17 | Complete | 2026-02-04 |
| 15. Diagnostic Infrastructure | v3.0 | 3/3 | Complete | 2026-02-17 |
| 16. Test Corpus & Ground Truth | v3.0 | 0/3 | Not started | - |
| 17. Evaluation Framework | v3.0 | 0/TBD | Not started | - |
| 18. Quality Metrics & Results | v3.0 | 0/TBD | Not started | - |
| 19. Analysis & Calibration | v3.0 | 0/TBD | Not started | - |
| 20. Targeted Improvements | v3.0 | 0/TBD | Not started | - |
