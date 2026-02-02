# Requirements: scholardoc-ocr v2.0

**Defined:** 2026-02-02
**Core Value:** Produce accurate, RAG-ready OCR text from scanned academic PDFs with robust operational behavior.

## v2.0 Requirements

### Post-Processing

- [ ] **POST-01**: Unicode NFC normalization applied to all extracted text (Tesseract and Surya output unified)
- [ ] **POST-02**: Soft hyphens (U+00AD) stripped from output
- [ ] **POST-03**: Ligatures decomposed to ASCII equivalents (fi, fl, ff, ffi, ffl)
- [ ] **POST-04**: Line breaks within paragraphs normalized to spaces; paragraph boundaries preserved
- [ ] **POST-05**: Hyphenated words split across lines rejoined (basic pattern: word-\nword)
- [ ] **POST-06**: Language-aware dehyphenation — German compounds and French hyphenated names preserved as intentional hyphens
- [ ] **POST-07**: Punctuation normalized (whitespace around punctuation, double spaces collapsed)

### Robustness

- [ ] **ROBU-01**: Structured multiprocess logging via QueueHandler/QueueListener — worker logs reach main process on macOS
- [ ] **ROBU-02**: Environment validation on startup — tesseract binary, required language packs, TMPDIR writable
- [ ] **ROBU-03**: Full tracebacks captured in all error paths (no more empty str(exc))
- [ ] **ROBU-04**: Work directory cleaned up on successful completion
- [ ] **ROBU-05**: `--keep-intermediates` flag to preserve work directory for debugging
- [ ] **ROBU-06**: Worker timeout protection — individual file processing has configurable timeout
- [ ] **ROBU-07**: Per-worker log files with process ID prefix for debugging parallel runs
- [ ] **ROBU-08**: Startup diagnostic report (log tesseract version, available langs, TMPDIR, Python version)

### Output

- [ ] **OUTP-01**: JSON metadata file written alongside output PDF (quality scores per page, surya fallback pages, processing stats)
- [ ] **OUTP-02**: `--extract-text` CLI flag triggers post-processing pipeline and writes .txt alongside output
- [ ] **OUTP-03**: MCP async job handling — long OCR runs return job ID immediately, `ocr_status(job_id)` endpoint for checking progress
- [ ] **OUTP-04**: MCP progress events emitted during processing (pages completed, current file)
- [ ] **OUTP-05**: `--json` CLI flag outputs structured JSON results to stdout

## v3.0 Requirements

### Advanced Quality

- **QUAL-01**: Dictionary-based spell correction suggestions (non-destructive)
- **QUAL-02**: Per-region quality scoring (not just per-page)
- **QUAL-03**: Image preprocessing pipeline (deskew, denoise, binarization via cv2)

### Configuration

- **CONF-01**: `.scholardoc-ocr.yaml` config file support
- **CONF-02**: Configurable post-processing transform chain (enable/disable individual transforms)

### Post-Processing Advanced

- **POST-08**: Header/footer detection and stripping
- **POST-09**: Footnote detection and separation
- **POST-10**: N-gram perplexity scoring for quality assessment

## Out of Scope

| Feature | Reason |
|---------|--------|
| Spell-check auto-correction | Destructive for academic texts — changes author names, technical terms, non-English words |
| Per-page post-processing only | Cross-page hyphens require full-document processing; per-page is lossy |
| Real-time streaming OCR results | Complexity vs. value — async jobs with status polling is sufficient |
| Custom Tesseract training data | Out of scope for this tool — use Tesseract and Surya models as-is |
| Layout analysis for post-processing | Research needed; defer to v3.0 (header/footer, footnotes) |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| POST-01 | — | Pending |
| POST-02 | — | Pending |
| POST-03 | — | Pending |
| POST-04 | — | Pending |
| POST-05 | — | Pending |
| POST-06 | — | Pending |
| POST-07 | — | Pending |
| ROBU-01 | — | Pending |
| ROBU-02 | — | Pending |
| ROBU-03 | — | Pending |
| ROBU-04 | — | Pending |
| ROBU-05 | — | Pending |
| ROBU-06 | — | Pending |
| ROBU-07 | — | Pending |
| ROBU-08 | — | Pending |
| OUTP-01 | — | Pending |
| OUTP-02 | — | Pending |
| OUTP-03 | — | Pending |
| OUTP-04 | — | Pending |
| OUTP-05 | — | Pending |

**Coverage:**
- v2.0 requirements: 20 total
- Mapped to phases: 0
- Unmapped: 20 (pending roadmap)

---
*Requirements defined: 2026-02-02*
*Last updated: 2026-02-02 after initial definition*
