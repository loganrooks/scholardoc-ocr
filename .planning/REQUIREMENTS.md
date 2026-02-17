# Requirements: scholardoc-ocr v3.0

**Defined:** 2026-02-17
**Core Value:** Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.

## v3.0 Requirements

Requirements for Diagnostic Intelligence milestone. Each maps to roadmap phases.

### Diagnostic Instrumentation

- [ ] **DIAG-01**: Pipeline captures image quality metrics per page (effective DPI, contrast/dynamic range, blur via Laplacian variance, skew angle via Hough transform) when --diagnostics flag is enabled
- [ ] **DIAG-02**: Pipeline captures per-signal quality breakdown (garbled score, dictionary score, confidence score, composite weights used) in diagnostic output alongside composite score
- [ ] **DIAG-03**: Pipeline detects and flags signal disagreement when any two quality signals differ by >0.3
- [ ] **DIAG-04**: Pipeline preserves Tesseract text before Surya overwrite and computes structured diff (additions, deletions, substitutions) when both engines process a page
- [ ] **DIAG-05**: Pipeline tracks post-processing changes (count of dehyphenations, paragraph joins, unicode normalizations, punctuation fixes) per page
- [ ] **DIAG-06**: Each page receives a struggle category (bad_scan, character_confusion, vocabulary_miss, layout_error, language_confusion, signal_disagreement, gray_zone, surya_insufficient) based on diagnostic signals
- [ ] **DIAG-07**: Diagnostic data attaches to PageResult via optional diagnostics field, backward-compatible with existing consumers
- [ ] **DIAG-08**: Diagnostic JSON sidecar includes full per-page diagnostic breakdown when --diagnostics is enabled

### Test Corpus & Ground Truth

- [ ] **CORP-01**: Test corpus directory (tests/corpus/) with gitignored PDF symlinks and committed corpus.json manifest describing each document's metadata and challenge profile
- [ ] **CORP-02**: Initial corpus includes 4 philosophy PDFs: Simondon Technical Objects, Derrida Of Grammatology, Derrida Margins of Philosophy, Derrida Dissemination
- [ ] **CORP-03**: Ground truth text files for 10-20 selected pages per corpus document, stored in tests/corpus/ground_truth/
- [ ] **CORP-04**: Diagnostic baseline run captured for all corpus documents with full diagnostic output stored in tests/corpus/baselines/

### Evaluation Framework

- [ ] **EVAL-01**: Evaluation runner invokes claude CLI and codex CLI as subprocesses with structured JSON output, abstracted behind common interface
- [ ] **EVAL-02**: Versioned prompt templates stored as files in eval/templates/ with content-addressable IDs for reproducibility
- [ ] **EVAL-03**: Evaluation error taxonomy defines categories (character_substitution, missing_text, inserted_text, layout_confusion, language_error, punctuation_error, word_boundary_error, garbled) with severity levels (critical/major/minor)
- [ ] **EVAL-04**: Smart page selection algorithm generates evaluation manifest from diagnostic data: all flagged pages, gray zone pages (threshold ±0.05), signal disagreement pages, plus stratified control sample
- [ ] **EVAL-05**: CER/WER/MER metrics computed against ground truth text using jiwer library, stored per page and aggregated per document
- [ ] **EVAL-06**: Evaluation results stored as structured JSON with schema version, template version, evaluator identity, and timestamp for cross-run comparison
- [ ] **EVAL-07**: CLI subcommand `ocr evaluate` runs evaluation workflow on existing OCR output without re-running the pipeline
- [ ] **EVAL-08**: Multi-evaluator support: same template produces comparable results from both claude and codex evaluators, with disagreement flagging

### Analysis & Calibration

- [ ] **ANLZ-01**: Score distribution analysis computes per-signal and composite score distributions across corpus documents
- [ ] **ANLZ-02**: Threshold sensitivity analysis tests quality threshold at multiple values (0.70-0.95 in 0.05 steps) and reports impact on flagging rates
- [ ] **ANLZ-03**: Signal correlation analysis computes Pearson/Spearman correlation between each quality signal and ground truth CER/WER
- [ ] **ANLZ-04**: False positive/negative detection identifies pages where quality scoring disagrees with ground truth evaluation (scored good but actually bad, or vice versa)
- [ ] **ANLZ-05**: Human-readable analysis report with recommendations for threshold, weight, and signal floor adjustments — outputs recommendations only, human applies changes

### Targeted Improvements

- [ ] **IMPR-01**: Quality threshold and signal weights adjusted based on analysis findings, with before/after evaluation comparison
- [ ] **IMPR-02**: Dictionary whitelist expanded based on false positive analysis (legitimate terms flagged as garbled)
- [ ] **IMPR-03**: Image preprocessing applied where diagnostic data shows clear benefit (scope determined by analysis — candidates: deskew, denoise, contrast normalization)
- [ ] **IMPR-04**: Re-evaluation after improvements demonstrates measurable quality gain on corpus documents

## Future Requirements

Deferred beyond v3.0. Tracked for future consideration.

### Evaluation Enhancements

- **EVAL-F01**: Evaluation dashboard — single HTML file with per-page results, CER/WER trends, struggle categories, before/after diffs
- **EVAL-F02**: Layout complexity scoring via LayoutPredictor (expensive model load, evaluation-only)
- **EVAL-F03**: Corpus expansion beyond philosophy texts for broader calibration validity

### Pipeline Enhancements

- **PIPE-F01**: Config file support (.scholardoc-ocr.yaml) for persistent settings
- **PIPE-F02**: Per-region quality scoring for mixed-quality pages
- **PIPE-F03**: N-gram perplexity scoring as additional quality signal

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| API-based LLM evaluation (Anthropic/OpenAI SDK) | User has CLI accounts; SDK adds dependency and credential management |
| Real-time evaluation during pipeline | Makes OCR 10-100x slower; evaluation must be post-hoc |
| Full-corpus evaluation (every page) | Wasteful; smart page selection provides 80-90% insight at 10-20% cost |
| Automated threshold/weight adjustment | Requires human domain expertise; analysis outputs recommendations only |
| Custom OCR model training | Massive scope, requires thousands of labeled pages, ML infrastructure |
| CI-integrated evaluation | LLM evaluation is non-deterministic and slow, insufficient corpus for statistical significance |
| PDF annotation overlay | Visual annotation adds complexity without proportional diagnostic value |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DIAG-01 | — | Pending |
| DIAG-02 | — | Pending |
| DIAG-03 | — | Pending |
| DIAG-04 | — | Pending |
| DIAG-05 | — | Pending |
| DIAG-06 | — | Pending |
| DIAG-07 | — | Pending |
| DIAG-08 | — | Pending |
| CORP-01 | — | Pending |
| CORP-02 | — | Pending |
| CORP-03 | — | Pending |
| CORP-04 | — | Pending |
| EVAL-01 | — | Pending |
| EVAL-02 | — | Pending |
| EVAL-03 | — | Pending |
| EVAL-04 | — | Pending |
| EVAL-05 | — | Pending |
| EVAL-06 | — | Pending |
| EVAL-07 | — | Pending |
| EVAL-08 | — | Pending |
| ANLZ-01 | — | Pending |
| ANLZ-02 | — | Pending |
| ANLZ-03 | — | Pending |
| ANLZ-04 | — | Pending |
| ANLZ-05 | — | Pending |
| IMPR-01 | — | Pending |
| IMPR-02 | — | Pending |
| IMPR-03 | — | Pending |
| IMPR-04 | — | Pending |

**Coverage:**
- v3.0 requirements: 29 total
- Mapped to phases: 0 (pending roadmap creation)
- Unmapped: 29

---
*Requirements defined: 2026-02-17*
*Last updated: 2026-02-17 after initial definition*
