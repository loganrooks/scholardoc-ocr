# External Integrations

**Analysis Date:** 2026-01-28

## APIs & External Services

**OCR Services:**
- Tesseract OCR - System-level OCR via ocrmypdf
  - SDK/Client: `ocrmypdf` Python package
  - Invocation: Subprocess call via `subprocess.run()` in `src/scholardoc_ocr/processor.py:141-182`
  - Auth: None (local binary)
  - Languages: eng, fra, ell, lat (configurable at `ProcessorConfig.langs_tesseract`)

- Surya OCR - Neural OCR model via Marker
  - SDK/Client: `marker-pdf` package with `marker.converters.pdf.PdfConverter`
  - Auth: None (local inference)
  - Languages: en, fr, el, la (hardcoded at `ProcessorConfig.langs_surya`)
  - Model loading: Cached via `marker.models.create_model_dict()` called once per batch

## Data Storage

**Databases:**
- None detected

**File Storage:**
- Local filesystem only
- Input: User-specified directory via `--input-dir` argument, defaults to `.` (current directory)
- Output: User-specified via `--output` flag, defaults to `<input_dir>/ocr_output`
  - Text files: `<output_dir>/final/<filename>.txt` (UTF-8 encoded)
  - PDF files: `<output_dir>/final/<filename>.pdf` (searchable PDFA format)
  - Work/intermediate: `<output_dir>/work/` (temporary, cleaned up)

**Caching:**
- Surya model cache: In-memory during batch processing in `src/scholardoc_ocr/processor.py:245-333`
- No persistent cache between runs

## Authentication & Identity

**Auth Provider:**
- None - Pipeline is fully local, no external authentication required

## Monitoring & Observability

**Error Tracking:**
- None detected (no integration with Sentry, Datadog, etc.)

**Logs:**
- Standard Python logging module via `logging.getLogger()`
- Configured in `cli.py:85-89` with format: `%(asctime)s | %(levelname)s | %(message)s`
- Log level: DEBUG (if `--verbose`) or INFO (default)
- Debug output suppressed for ocrmypdf/PIL at `processor.py:150-151`
- Rich library used for terminal UI output (progress, tables) in `pipeline.py`

## CI/CD & Deployment

**Hosting:**
- None - Command-line tool designed for local/standalone use

**CI Pipeline:**
- Not detected (no GitHub Actions, GitLab CI, etc. configuration)

## Environment Configuration

**Required env vars:**
- None - All configuration via CLI arguments

**Secrets location:**
- Not applicable (no API keys or secrets)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- Progress callbacks supported in `run_surya_batch()` via optional `progress_callback` parameter in `processor.py:250`
- Callback signature: `callable(stage: str, current: int, total: int)` for batch OCR progress reporting
- Used by pipeline to update live progress display in `pipeline.py:536-549`

## File Format Support

**Input:**
- PDF files only (`.pdf` extension)
- Auto-discovered via `glob()` or `rglob()` (if `--recursive`)
- Specific files via `--files` argument

**Output:**
- PDF: PDFA format (searchable with embedded text layer)
- Text: UTF-8 plaintext, one page text block separated by `\n\n`

---

*Integration audit: 2026-01-28*
