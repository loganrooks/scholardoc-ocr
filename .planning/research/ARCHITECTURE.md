# Architecture Research: Diagnostic Intelligence & Evaluation Framework

**Domain:** OCR Pipeline Diagnostic Enrichment, LLM-Based Evaluation, Quality Calibration
**Researched:** 2026-02-17
**Confidence:** HIGH (based on full codebase analysis + verified external documentation)

## Current Architecture Summary

The existing pipeline has clean layered separation:

```
Entry Points (cli.py, mcp_server.py)
       |
       v
Orchestration (pipeline.py: PipelineConfig, run_pipeline)
       |
       +---> Phase 1: Parallel Tesseract (_tesseract_worker via ProcessPoolExecutor)
       |         |
       |         v
       |    Quality Analysis (quality.py: QualityAnalyzer, _GarbledSignal)
       |    + confidence.py (ConfidenceSignal) + dictionary.py (DictionarySignal)
       |         |
       |         v
       |    types.py: PageResult(page_number, status, quality_score, engine, flagged, text)
       |
       +---> Phase 2: Cross-File Batched Surya (batch.py, surya.py, model_cache.py)
       |         |
       |         v
       |    Re-analysis with QualityAnalyzer, update PageResult in-place
       |
       v
Output: BatchResult -> FileResult[] -> PageResult[] + JSON metadata files
```

**Key integration surfaces for new work:**

1. `PageResult` -- the per-page data carrier (currently: page_number, status, quality_score, engine, flagged, text)
2. `QualityResult` -- the quality analysis output (currently: score, flagged, signal_scores, signal_details, snippets)
3. `_tesseract_worker` -- where Phase 1 processing happens per-file (in worker processes)
4. `run_pipeline` -- where Phase 2 and final output assembly happen (main process)
5. `FileResult.to_dict()` / `BatchResult.to_dict()` -- JSON serialization boundary

## System Overview: New Architecture

```
+===========================================================================+
|                      EXISTING PIPELINE (unchanged)                         |
|                                                                            |
|  CLI/MCP --> PipelineConfig --> run_pipeline()                             |
|    Phase 1: Tesseract (parallel) --> QualityAnalyzer --> PageResult[]      |
|    Phase 2: Surya (batched) --> Re-analyze --> Updated PageResult[]        |
|    Output: BatchResult with FileResult[] and JSON metadata                 |
+===========================================================================+
         |                                          |
         | (a) Enriched diagnostic                  | (b) Output artifacts
         |     data in PageResult                   |     (.json, .txt, .pdf)
         v                                          v
+--------------------+                   +------------------------+
| diagnostics.py     |                   | Evaluation Framework   |
| (NEW)              |                   | (NEW: eval/ package)   |
|                    |                   |                        |
| PageDiagnostics    |                   | eval/runner.py         |
|  - image_metrics   |                   |   invoke claude/codex  |
|  - signal_breakdown|                   |   as subprocess         |
|  - timing_data     |                   |                        |
|                    |                   | eval/templates/        |
|                    |                   |   prompt templates     |
| DiagnosticCollector|                   |   + JSON schemas       |
|  - hooks into      |                   |                        |
|    pipeline phases  |                   | eval/corpus.py         |
+--------------------+                   |   corpus management    |
         |                               |                        |
         v                               | eval/results.py        |
+--------------------+                   |   result storage +     |
| Output: enriched   |                   |   comparison           |
| .json files with   |                   +------------------------+
| diagnostic data    |                            |
+--------------------+                            v
                                         +------------------------+
                                         | Analysis / Calibration |
                                         | (NEW: analysis.py)     |
                                         |                        |
                                         | - Score distribution   |
                                         | - Threshold analysis   |
                                         | - Signal correlation   |
                                         | - False positive/neg   |
                                         +------------------------+
                                                   |
                                                   v
                                         +------------------------+
                                         | Targeted Improvements  |
                                         | (modifications to      |
                                         |  existing modules)     |
                                         |                        |
                                         | quality.py adjustments |
                                         | dictionary.py updates  |
                                         | postprocess.py tweaks  |
                                         +------------------------+
```

### Design Principle: Separation of Concerns

The four activities in the milestone context map to four distinct architectural boundaries:

| Activity | Where | Coupling to Pipeline |
|----------|-------|----------------------|
| (a) Diagnostic data capture | `diagnostics.py` + enriched `PageResult` | TIGHT -- runs during OCR |
| (b) Evaluation of OCR output | `eval/` package | LOOSE -- runs post-hoc on artifacts |
| (c) Analysis/calibration | `analysis.py` | NONE -- reads evaluation results |
| (d) Targeted improvements | Existing modules | TIGHT -- modifies quality/postprocess |

This separation is critical. Diagnostic capture must be lightweight and non-breaking during OCR runs. Evaluation is a completely separate workflow that reads output artifacts. Analysis consumes evaluation results. Improvements are code changes driven by analysis findings.

## Component Responsibilities

### New Components

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `diagnostics.py` | Collect and attach per-page diagnostic metrics during pipeline execution | Dataclass + collector pattern, called from `_tesseract_worker` and `run_pipeline` |
| `eval/runner.py` | Invoke claude/codex CLI as subprocess, pass prompts, parse JSON responses | subprocess.run with --output-format json, timeout handling, retry logic |
| `eval/templates/` | Store versioned prompt templates and JSON schemas for evaluation | Jinja2 or f-string templates + JSON Schema files, loaded by runner |
| `eval/corpus.py` | Manage test corpus: discover PDFs, track ground truth, handle symlinks | Path resolution, manifest file (corpus.json), gitignore-aware |
| `eval/results.py` | Store, load, compare evaluation results across runs | JSON files in eval_results/ directory, diff computation |
| `analysis.py` | Analyze score distributions, threshold sensitivity, signal correlations | Statistical functions operating on evaluation result datasets |

### Modified Components

| Component | Modification | Why |
|-----------|-------------|-----|
| `types.py` | Add optional `diagnostics` field to `PageResult` | Carry diagnostic data through pipeline without breaking existing consumers |
| `pipeline.py` | Call `DiagnosticCollector` at key points if diagnostics enabled | Capture timing, image metrics, signal details per page |
| `cli.py` | Add `--diagnostics` flag and `evaluate` subcommand | Enable diagnostic mode; provide CLI entry point for evaluation |
| `quality.py` | No structural changes yet -- improvements come from analysis findings | Threshold/weight adjustments driven by data, not architecture changes |

## Recommended Project Structure

```
src/scholardoc_ocr/
    # Existing modules (unchanged structure)
    __init__.py
    cli.py                    # Add --diagnostics flag, evaluate subcommand
    pipeline.py               # Add DiagnosticCollector hooks
    types.py                  # Add diagnostics field to PageResult
    quality.py                # Unchanged structurally (improvements later)
    confidence.py             # Unchanged
    dictionary.py             # Unchanged
    tesseract.py              # Unchanged
    surya.py                  # Unchanged
    processor.py              # Unchanged
    batch.py                  # Unchanged
    model_cache.py            # Unchanged
    callbacks.py              # Unchanged
    postprocess.py            # Unchanged
    device.py                 # Unchanged
    timing.py                 # Unchanged
    logging_.py               # Unchanged
    environment.py            # Unchanged
    exceptions.py             # Unchanged
    mcp_server.py             # Unchanged

    # NEW: Diagnostic data capture (runs during pipeline)
    diagnostics.py            # PageDiagnostics dataclass, DiagnosticCollector

    # NEW: Analysis utilities (runs on collected data)
    analysis.py               # Score distribution, threshold analysis, correlations

    # NEW: Evaluation framework (separate workflow, not pipeline)
    eval/
        __init__.py
        runner.py             # Subprocess invocation of claude/codex CLI
        templates/            # Prompt templates + JSON schemas
            quality_eval.txt  # Template for quality evaluation
            quality_eval_schema.json
            comparison.txt    # Template for A/B comparison
            comparison_schema.json
            faithfulness.txt  # Template for faithfulness check
            faithfulness_schema.json
        corpus.py             # Test corpus management
        results.py            # Result storage and comparison
        cli_adapter.py        # Abstraction over claude/codex CLI differences

# NEW: Test corpus directory (gitignored, symlinked PDFs)
tests/
    corpus/                   # Gitignored directory
        corpus.json           # Manifest: file metadata, ground truth refs
        pdfs/                 # Symlinks to actual PDFs
        ground_truth/         # Expected text per page (manually curated)
        README.md             # Instructions for setting up corpus

# NEW: Evaluation results directory (gitignored)
eval_results/
    runs/                     # Per-run results
        2026-02-17T10-30-00/
            run_config.json   # What was evaluated, which evaluator
            results.json      # Per-page evaluation scores
            summary.json      # Aggregated metrics
    baselines/                # Saved baseline results for comparison
```

### Structure Rationale

- **`diagnostics.py` in main package:** Diagnostic collection runs during pipeline execution, so it must be importable from `pipeline.py` and `_tesseract_worker`. Keeping it as a single module (not a subpackage) matches the existing flat module pattern.

- **`eval/` as subpackage:** Evaluation is a separate workflow with multiple components (runner, templates, corpus, results). It never runs during OCR -- it runs afterward. A subpackage keeps this boundary clear and prevents accidental coupling.

- **`analysis.py` in main package:** Analysis operates on evaluation result data and produces recommendations. It is a utility module, not a subpackage, because it is a single responsibility (statistical analysis of scores).

- **`tests/corpus/` separate from `tests/`:** The corpus contains large binary PDF files that must never be committed. Using symlinks lets developers point to their own PDF collections. The `corpus.json` manifest IS committed and describes expected files.

- **`eval_results/` at project root:** Evaluation results are ephemeral artifacts like build output. They are gitignored but readable by analysis scripts. The directory structure (runs + baselines) supports comparing results across time.

## Architectural Patterns

### Pattern 1: Optional Diagnostic Enrichment

**What:** Add diagnostic data to `PageResult` without changing its core interface or breaking any existing consumer.

**When to use:** Any time you want to attach extra metadata to pipeline results that only some consumers care about.

**Trade-offs:** Slight memory overhead when diagnostics enabled; no overhead when disabled. Existing code that calls `page_result.to_dict()` continues to work.

**Example:**

```python
# types.py -- add optional field
@dataclass
class PageResult:
    page_number: int
    status: PageStatus
    quality_score: float
    engine: OCREngine
    flagged: bool = False
    text: str | None = None
    diagnostics: dict | None = None  # NEW: optional diagnostic data

    def to_dict(self, include_text: bool = False) -> dict:
        d: dict = {
            "page_number": self.page_number,
            "status": str(self.status),
            "quality_score": self.quality_score,
            "engine": str(self.engine),
            "flagged": self.flagged,
        }
        if include_text and self.text is not None:
            d["text"] = self.text
        if self.diagnostics is not None:  # NEW: only include when present
            d["diagnostics"] = self.diagnostics
        return d
```

```python
# diagnostics.py
@dataclass
class PageDiagnostics:
    """Rich diagnostic data for a single page."""

    # Image quality metrics (from PyMuPDF pixmap analysis)
    image_dpi: int | None = None
    image_count: int = 0
    has_embedded_text: bool = False
    text_char_count: int = 0

    # Quality signal breakdown (from QualityAnalyzer)
    signal_scores: dict[str, float] = field(default_factory=dict)
    signal_details: dict[str, dict] = field(default_factory=dict)

    # Timing data
    extraction_time_ms: float = 0.0
    analysis_time_ms: float = 0.0
    ocr_time_ms: float = 0.0

    # Decision trace
    decision: str = ""  # "existing_good", "tesseract_good", "flagged_for_surya", etc.
    threshold_used: float = 0.85
    score_before_ocr: float | None = None
    score_after_ocr: float | None = None

    def to_dict(self) -> dict:
        """Serialize for JSON output. Omit None values."""
        d = {}
        for k, v in self.__dict__.items():
            if v is not None and v != 0 and v != 0.0 and v != "" and v != {}:
                d[k] = v
        return d
```

### Pattern 2: CLI Subprocess Evaluator

**What:** Invoke `claude` or `codex` CLI as a subprocess with structured prompts and parse JSON responses. Abstract over CLI differences with a common adapter.

**When to use:** For LLM-based evaluation of OCR output quality, where we want to use frontier models as judges without embedding an API client in the project.

**Trade-offs:** Depends on CLI tools being installed. Subprocess invocation is slower than direct API calls but avoids API key management and dependency coupling. JSON schema enforcement ensures parseable responses.

**Example:**

```python
# eval/cli_adapter.py
from dataclasses import dataclass
from enum import StrEnum

class EvaluatorEngine(StrEnum):
    CLAUDE = "claude"
    CODEX = "codex"

@dataclass
class EvaluatorConfig:
    engine: EvaluatorEngine = EvaluatorEngine.CLAUDE
    model: str | None = None  # None = default model
    timeout: int = 120
    max_retries: int = 2

def build_command(
    config: EvaluatorConfig,
    prompt: str,
    json_schema: dict | None = None,
) -> list[str]:
    """Build subprocess command for the configured evaluator engine."""
    if config.engine == EvaluatorEngine.CLAUDE:
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if json_schema is not None:
            import json
            cmd.extend(["--json-schema", json.dumps(json_schema)])
        if config.model:
            cmd.extend(["--model", config.model])
        return cmd

    elif config.engine == EvaluatorEngine.CODEX:
        cmd = ["codex", "exec", prompt, "--json"]
        if json_schema is not None:
            # Write schema to temp file for codex --output-schema
            import json
            import tempfile
            schema_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False
            )
            json.dump(json_schema, schema_file)
            schema_file.close()
            cmd.extend(["--output-schema", schema_file.name])
        return cmd

    raise ValueError(f"Unknown engine: {config.engine}")
```

```python
# eval/runner.py
import json
import subprocess

def run_evaluation(
    config: EvaluatorConfig,
    prompt: str,
    json_schema: dict | None = None,
) -> dict:
    """Run a single evaluation and return parsed JSON result."""
    cmd = build_command(config, prompt, json_schema)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=config.timeout,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Evaluator failed: {result.stderr}")

    response = json.loads(result.stdout)

    # Claude returns structured_output when --json-schema used
    if config.engine == EvaluatorEngine.CLAUDE and json_schema:
        return response.get("structured_output", response.get("result", {}))

    return response
```

### Pattern 3: Template-Driven Evaluation

**What:** Store evaluation prompts as template files with placeholder substitution, paired with JSON schemas that enforce response structure. Version templates alongside code.

**When to use:** When evaluation criteria may evolve and you want to iterate on prompts without changing code.

**Trade-offs:** Templates add a layer of indirection but enable non-code changes to evaluation criteria. JSON schemas ensure responses are always parseable.

**Example:**

```python
# eval/templates/quality_eval.txt
You are evaluating OCR output quality for an academic text.

## Source Information
- Filename: {filename}
- Page: {page_number}
- OCR Engine: {engine}
- Quality Score (automated): {quality_score}

## OCR Text Output
```
{ocr_text}
```

## Evaluation Criteria
Rate the following on a scale of 1-5:
1. **Readability**: Is the text readable and coherent?
2. **Completeness**: Does it appear to capture all text from the page?
3. **Accuracy**: Are words spelled correctly? Are there garbled sections?
4. **Formatting**: Are paragraphs, headings, and structure preserved?
5. **Academic Fidelity**: Are citations, footnotes, and special terms preserved?

Provide an overall quality rating (1-5) and explain any issues found.
```

```json
// eval/templates/quality_eval_schema.json
{
  "type": "object",
  "required": ["readability", "completeness", "accuracy", "formatting",
               "academic_fidelity", "overall", "issues"],
  "properties": {
    "readability": {"type": "integer", "minimum": 1, "maximum": 5},
    "completeness": {"type": "integer", "minimum": 1, "maximum": 5},
    "accuracy": {"type": "integer", "minimum": 1, "maximum": 5},
    "formatting": {"type": "integer", "minimum": 1, "maximum": 5},
    "academic_fidelity": {"type": "integer", "minimum": 1, "maximum": 5},
    "overall": {"type": "integer", "minimum": 1, "maximum": 5},
    "issues": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "category": {"type": "string"},
          "description": {"type": "string"},
          "severity": {"type": "string", "enum": ["low", "medium", "high"]}
        }
      }
    }
  }
}
```

### Pattern 4: Corpus Manifest

**What:** A committed JSON manifest describing the test corpus structure, with actual PDF files gitignored and referenced via symlinks. Ground truth text is committed as plain text files.

**When to use:** When test data is too large or sensitive to commit but you need reproducible evaluation.

**Trade-offs:** Requires manual corpus setup per machine. Manifest ensures consistency even when corpus files differ.

**Example:**

```json
// tests/corpus/corpus.json
{
  "version": 1,
  "description": "ScholarDoc OCR evaluation corpus",
  "files": [
    {
      "id": "heidegger-bt",
      "filename": "heidegger-being-and-time.pdf",
      "pages": 589,
      "languages": ["en", "de"],
      "characteristics": ["dense_philosophy", "german_terms", "footnotes"],
      "ground_truth_pages": [1, 2, 3, 45, 100],
      "notes": "Macquarrie/Robinson translation with heavy German terminology"
    },
    {
      "id": "levinas-ti",
      "filename": "levinas-totality-infinity.pdf",
      "pages": 307,
      "languages": ["en", "fr"],
      "characteristics": ["french_terms", "long_sentences"],
      "ground_truth_pages": [1, 10, 50],
      "notes": "Lingis translation with French philosophical vocabulary"
    }
  ],
  "setup_instructions": "Symlink PDFs into tests/corpus/pdfs/. See README.md."
}
```

## Data Flow

### Flow 1: Diagnostic Data Capture (During Pipeline)

```
_tesseract_worker() or run_pipeline()
         |
         v
   Extract text (processor.py)
         |
         +---> DiagnosticCollector.record_extraction(page, timing)
         |
         v
   Analyze quality (quality.py)
         |
         +---> DiagnosticCollector.record_analysis(page, quality_result)
         |
         v
   OCR if needed (tesseract.py or surya.py)
         |
         +---> DiagnosticCollector.record_ocr(page, engine, timing)
         |
         v
   Build PageResult with diagnostics attached
         |
         v
   FileResult.to_dict() includes diagnostics in JSON output
```

**Key constraint:** `_tesseract_worker` runs in a subprocess via ProcessPoolExecutor. The DiagnosticCollector must be instantiable in worker processes (no singletons, no shared state). Each worker creates its own collector and attaches data to PageResult before returning.

### Flow 2: Evaluation Workflow (Post-Hoc, Separate from Pipeline)

```
User runs: ocr evaluate tests/corpus/pdfs/ --evaluator claude

         |
         v
   1. Discover corpus (corpus.py)
      - Read corpus.json manifest
      - Verify PDFs exist via symlinks
      - Load ground truth text for reference pages
         |
         v
   2. Run OCR pipeline on corpus PDFs (reuse run_pipeline)
      - With --diagnostics enabled
      - Output to eval_results/runs/<timestamp>/
         |
         v
   3. For each page with ground truth:
      - Load template (templates/quality_eval.txt)
      - Substitute page data into template
      - Invoke evaluator (runner.py -> subprocess claude/codex)
      - Parse JSON response (structured_output)
      - Store per-page evaluation scores
         |
         v
   4. Aggregate results (results.py)
      - Per-file and per-page scores
      - Correlation with automated quality_score
      - Write summary.json
         |
         v
   5. Optional: Compare against baseline
      - Load previous baseline from eval_results/baselines/
      - Compute deltas
      - Flag regressions
```

### Flow 3: Analysis and Calibration

```
User runs: ocr analyze eval_results/runs/2026-02-17T10-30-00/

         |
         v
   analysis.py loads:
   - Pipeline diagnostic data (from enriched .json)
   - Evaluation results (from eval runner output)
   - Ground truth annotations (from corpus)
         |
         v
   Compute:
   - Score distribution histograms
   - Threshold sensitivity: at what threshold does flag rate change?
   - Signal correlation: which signals predict LLM evaluation scores?
   - False positive analysis: pages flagged but LLM says quality is fine
   - False negative analysis: pages not flagged but LLM finds issues
   - Per-signal contribution analysis
         |
         v
   Output:
   - analysis_report.json (machine-readable)
   - analysis_report.txt (human-readable summary)
   - Specific recommendations:
     "Raise garbled weight from 0.4 to 0.5"
     "Add word 'apodeictic' to dictionary whitelist"
     "Lower confidence floor from 0.3 to 0.2"
```

### Flow 4: Smart Page Selection for Evaluation

Not every page needs LLM evaluation (expensive). Smart selection prioritizes:

```
All pages in corpus
         |
         v
   Filter 1: Pages with ground truth  --> always evaluate
         |
         v
   Filter 2: Gray zone pages          --> quality_score within
             (threshold +/- 0.05)         GRAY_ZONE of threshold
         |
         v
   Filter 3: Engine-transition pages   --> pages where Tesseract
             (Surya was triggered)         flagged and Surya ran
         |
         v
   Filter 4: Random sample of          --> statistical coverage
             remaining pages               without exhaustive eval
         |
         v
   Selected pages for evaluation
```

This integrates with the existing `QualityAnalyzer.GRAY_ZONE = 0.05` constant and the `PageResult.flagged` / `PageResult.engine` fields.

## Integration Points

### Where Diagnostic Metrics Attach

**Decision: Enrich `PageResult.diagnostics` as optional dict field.**

Rationale:
- `PageResult` already flows through the entire pipeline
- Adding `diagnostics: dict | None = None` is backward-compatible
- `to_dict()` already supports conditional inclusion (see `include_text`)
- A dict (not a separate dataclass) keeps serialization simple and avoids import cycles in worker processes
- The `diagnostics.py` module provides `PageDiagnostics.to_dict()` for construction

**Rejected alternative:** Separate `DiagnosticResult` dataclass linked by page number. This would require joining data structures at output time and adds complexity without benefit since the data naturally belongs to the page.

### Where Image Quality Analysis Integrates

**Decision: Before Tesseract, during the extraction phase in `_tesseract_worker`.**

The extraction phase already calls `processor.extract_text_by_page()` which opens the PDF with PyMuPDF. Image quality metrics (DPI, image count, text presence) can be collected from the same `fitz.Document` handle without re-opening the file.

```python
# In _tesseract_worker, after extract_text_by_page:
if diagnostics_enabled:
    image_metrics = collect_image_metrics(input_path)  # uses fitz
    # Attach to each page's diagnostic data later
```

**Not after Tesseract:** By then we have already committed to OCR. Pre-OCR image metrics help explain WHY quality is low.

**Not as a separate pass:** Opening the PDF twice is wasteful. The extraction phase is the natural place.

### Where the Evaluation Framework Lives

**Decision: New `eval/` subpackage within `src/scholardoc_ocr/`.**

- It is part of the scholardoc_ocr package for import convenience
- It is a subpackage (not flat module) because it has multiple components
- It is never imported by the pipeline itself -- only by CLI evaluation commands
- Templates and schemas live as data files within the subpackage

**Rejected alternative:** Separate top-level package (e.g., `scholardoc_eval`). Adds packaging complexity for no real benefit. The eval code shares types with the main package.

### How Evaluation Templates Get Versioned

**Decision: Templates stored as files in `eval/templates/`, committed to git, loaded at runtime.**

- Each template is a `.txt` file (prompt) paired with a `.json` file (JSON schema)
- Templates use simple `{placeholder}` substitution (not Jinja2) to avoid dependencies
- Template "versions" are tracked by git history, not explicit version numbers
- A `TEMPLATES.md` file in the templates directory documents each template's purpose

### How CLI-Based Evaluator Invocations Get Orchestrated

**Decision: `eval/cli_adapter.py` abstracts over `claude` and `codex` CLI differences.**

Both tools support:
- Non-interactive prompt execution (`claude -p` / `codex exec`)
- JSON output (`--output-format json` / `--json`)
- Schema enforcement (`--json-schema` / `--output-schema`)

The adapter provides a unified `run_evaluation(config, prompt, schema)` function. The runner handles retries, timeouts, and error normalization.

### How the Test Corpus Integrates

**Decision: `tests/corpus/` directory with committed manifest, gitignored PDFs.**

- `corpus.json` manifest is committed -- describes expected files and their characteristics
- `pdfs/` subdirectory is gitignored -- contains symlinks to actual PDF files
- `ground_truth/` contains manually curated text for specific pages (committed)
- `README.md` explains setup for new developers

The `eval/corpus.py` module reads the manifest and validates that expected files exist.

## Internal Boundaries

| Boundary | Communication | Coupling | Notes |
|----------|---------------|----------|-------|
| pipeline.py <-> diagnostics.py | Direct function call | TIGHT | DiagnosticCollector called from worker |
| pipeline.py <-> eval/ | NONE | ZERO | Eval never runs during pipeline |
| eval/runner.py <-> claude/codex CLI | subprocess.run | LOOSE | JSON over stdout |
| eval/results.py <-> analysis.py | File I/O (JSON) | LOOSE | Analysis reads result files |
| analysis.py <-> quality.py | Information flow only | NONE | Analysis outputs recommendations, human applies changes |
| types.py <-> diagnostics.py | PageResult.diagnostics field | TIGHT | Core data enrichment |

## Scaling Considerations

| Concern | 10 pages evaluated | 100 pages evaluated | 1000 pages evaluated |
|---------|--------------------|---------------------|----------------------|
| Evaluation cost | ~$0.50 (LLM calls) | ~$5 | ~$50 |
| Evaluation time | ~2 min | ~20 min | ~3 hours |
| Result storage | ~50KB JSON | ~500KB JSON | ~5MB JSON |
| Diagnostic data overhead | Negligible | ~1MB extra in output | ~10MB extra |

### Scaling Priorities

1. **First bottleneck: LLM evaluation cost and time.** Smart page selection (gray zone + ground truth pages) reduces evaluated pages from N to ~0.1N-0.2N. This is the single most important optimization.

2. **Second bottleneck: Diagnostic data in worker processes.** The `_tesseract_worker` runs in subprocess. Diagnostic collection must be lightweight (no GPU operations, no network calls). Use only PyMuPDF operations that are already happening.

3. **Not a bottleneck: Result storage.** JSON files are small even for large corpora.

## Anti-Patterns

### Anti-Pattern 1: Coupling Evaluation to Pipeline Execution

**What people do:** Run LLM evaluation inside `run_pipeline()` after each page.
**Why it's wrong:** Evaluation is expensive (1-2s per page via LLM). Pipeline should finish fast. Mixing concerns makes pipeline untestable without LLM access.
**Do this instead:** Pipeline captures diagnostic data. Evaluation runs separately as a post-hoc workflow.

### Anti-Pattern 2: Storing Ground Truth in the Repository

**What people do:** Commit large PDF files and expected-output text files to git.
**Why it's wrong:** PDFs are large binaries. Git is bad at binary diffs. Repository bloats.
**Do this instead:** Commit only the manifest (corpus.json) and ground truth text files. PDFs referenced via symlinks, gitignored.

### Anti-Pattern 3: Unversioned Prompt Templates

**What people do:** Embed evaluation prompts as Python string literals in code.
**Why it's wrong:** Changing prompts requires code changes. Hard to track what prompt produced what results. Can not iterate on prompts independently of code.
**Do this instead:** Store templates as files. Load at runtime. Git tracks template history.

### Anti-Pattern 4: Making DiagnosticCollector a Singleton

**What people do:** Create a global singleton diagnostic collector for the whole pipeline.
**Why it's wrong:** `_tesseract_worker` runs in subprocess pools. Singletons do not survive process boundaries. Each worker needs its own collector.
**Do this instead:** Create a DiagnosticCollector per worker invocation. Attach collected data to PageResult before returning from the worker.

### Anti-Pattern 5: Returning Structured Analysis Recommendations as Automated Config Changes

**What people do:** Have the analysis module automatically update quality.py weights and thresholds.
**Why it's wrong:** Quality tuning requires human judgment. Automated changes could degrade quality for edge cases.
**Do this instead:** Output recommendations as a report. Human reviews and applies changes.

## Suggested Build Order

Based on dependencies:

### Phase 1: Diagnostic Infrastructure (Foundation)
1. Add `diagnostics: dict | None = None` to `PageResult`
2. Create `diagnostics.py` with `PageDiagnostics` dataclass
3. Add image metrics collection (reuse fitz during extraction)
4. Wire `DiagnosticCollector` into `_tesseract_worker`
5. Add `--diagnostics` flag to CLI
6. Enrich JSON metadata output with diagnostic data

**Depends on:** Nothing new. Only modifies existing types.py and pipeline.py.
**Enables:** Evaluation framework and analysis.

### Phase 2: Test Corpus Setup
1. Create `tests/corpus/` directory structure
2. Write `corpus.json` manifest schema
3. Create `eval/corpus.py` for corpus management
4. Add ground truth text for reference pages
5. Document corpus setup in README

**Depends on:** Nothing.
**Enables:** Evaluation runner.

### Phase 3: Evaluation Framework
1. Create `eval/cli_adapter.py` with claude/codex abstraction
2. Create `eval/runner.py` with subprocess invocation
3. Write initial prompt templates and JSON schemas
4. Create `eval/results.py` for result storage
5. Add `evaluate` CLI subcommand
6. Smart page selection logic

**Depends on:** Phase 2 (needs corpus). Phase 1 (uses diagnostic data in prompts).
**Enables:** Analysis.

### Phase 4: Analysis and Calibration
1. Create `analysis.py` with score distribution analysis
2. Add threshold sensitivity analysis
3. Add signal correlation analysis
4. Add false positive/negative detection
5. Generate human-readable reports

**Depends on:** Phase 3 (needs evaluation results).
**Enables:** Targeted improvements (Phase 5).

### Phase 5: Targeted Improvements
1. Apply findings from analysis to quality.py (weights, thresholds)
2. Expand dictionary.py whitelist based on false positive data
3. Improve postprocess.py transforms based on evaluation feedback
4. Re-run evaluation to measure improvement
5. Save baseline for regression detection

**Depends on:** Phase 4 (needs analysis findings).

## Sources

- [Claude Code Headless Mode Documentation](https://code.claude.com/docs/en/headless) -- CLI invocation with `-p`, `--output-format json`, `--json-schema` for structured evaluation output (HIGH confidence)
- [Codex CLI Reference](https://developers.openai.com/codex/cli/reference/) -- `codex exec`, `--json`, `--output-schema` for structured output (HIGH confidence)
- [OmniAI OCR Benchmark](https://getomni.ai/blog/ocr-benchmark) -- LLM-as-judge pattern for OCR evaluation using GPT-4o (MEDIUM confidence)
- [Pdfquad: PDF Quality Assessment](https://bitsgalore.org/2024/12/13/pdf-quality-assessment-for-digitisation-batches-with-python-pymupdf-and-pillow.html) -- PyMuPDF + Pillow for image quality metrics, DPI extraction, compression analysis (HIGH confidence)
- [OCR-D Ground Truth Corpus](https://github.com/OCR-D/gt_structure_text) -- Corpus management patterns for OCR ground truth (MEDIUM confidence)
- [PreP-OCR Pipeline](https://arxiv.org/html/2505.20429v1) -- Two-stage pipeline combining image restoration with semantic-aware post-OCR correction (MEDIUM confidence)
- [OCR Accuracy Metrics Survey](https://dl.acm.org/doi/10.1145/3476887.3476888) -- CER, WER, and structured evaluation metrics for OCR (HIGH confidence)
- Existing codebase analysis of all modules in `src/scholardoc_ocr/` (HIGH confidence)

---
*Architecture research for: Diagnostic Intelligence & Evaluation Framework*
*Researched: 2026-02-17*
