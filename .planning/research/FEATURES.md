# Feature Landscape

**Domain:** Academic text OCR pipeline (Continental philosophy / humanities)
**Researched:** 2026-02-02
**Confidence:** MEDIUM-HIGH (established OCR post-processing patterns; codebase analysis HIGH)

## Scope

This document covers two feature dimensions for v2.0:

1. **Post-processing pipeline** -- text normalization for RAG-ready output
2. **Production robustness** -- logging, validation, timeouts, cleanup

The v1 rearchitecture (library API, multi-signal quality, structured results) is already implemented. This builds on top of it.

## Table Stakes

Features users expect for "RAG-ready" output. Missing any means text requires manual cleanup before ingestion.

| Feature | Why Expected | Complexity | Depends On | Notes |
|---------|--------------|------------|------------|-------|
| **Dehyphenation** | Scanned academic texts hyphenate at line breaks; "phi-\nlosophy" must become "philosophy" for search/RAG | Low | Text extraction (exists) | Must handle soft hyphens (U+00AD), regular hyphens at line end. Preserve intentional hyphens ("well-known"). Use existing dictionary signal for ambiguous cases. |
| **Line break normalization** | OCR preserves physical line breaks from page layout; paragraphs must be rejoined for RAG chunking | Low | Text extraction (exists) | Single newline within paragraph -> space. Double newline -> paragraph break. Detect boundaries by blank lines, sentence-ending punctuation + capital letter. |
| **Unicode normalization (NFC)** | OCR engines produce inconsistent Unicode forms; combined chars vs precomposed break search/matching | Low | None | `unicodedata.normalize('NFC', text)`. Also fix: fi/fl/ffi ligature codepoints -> individual chars, NBSP -> space, zero-width chars -> remove. |
| **Punctuation normalization** | Mixed curly/straight quotes, inconsistent ellipsis, dash variants | Low | Unicode normalization | Normalize to consistent forms. For RAG: straight quotes safer. Normalize dash variants to canonical form. |
| **Environment validation at startup** | Missing tesseract binary or language packs produces cryptic errors deep in worker processes | Low | CLI (exists) | Check: tesseract binary, required lang packs, ocrmypdf importable, output dir writable. Print clear actionable errors. |
| **JSON metadata output** | Programmatic consumers (RAG pipelines, MCP) need structured results alongside text | Low | Pipeline result types (exist) | Write `{stem}.json` with: quality scores, engine per page, timing, flagged pages, languages. Serialize existing `FileResult`/`PageResult`. |
| **Structured multiprocess logging** | Worker process logs interleave; lose filename/phase context | Medium | Pipeline (exists) | `QueueHandler` in workers, `QueueListener` in main. Structured fields: filename, phase, page_number, worker_pid. |
| **Work directory cleanup** | `output_dir/work/` accumulates GBs of intermediate PDFs across runs | Low | Pipeline (exists) | Clean after successful completion. Keep on failure for debugging. Add `--keep-work` CLI flag. |

## Differentiators

Features beyond baseline that provide competitive advantage for the academic humanities use case.

| Feature | Value Proposition | Complexity | Depends On | Notes |
|---------|-------------------|------------|------------|-------|
| **Language-aware dehyphenation** | German compounds vs English hyphenation have different rules; "Selbst-\nbewusstsein" must rejoin differently than "self-\nawareness" | Medium | Dehyphenation, existing dictionary signal, language config | German: almost always rejoin. English: dictionary lookup. Greek transliterations: keep if unsure. Leverages existing `DictionarySignal` and language lists. |
| **Page header/footer stripping** | Running headers ("Chapter 3: Being and Time") and page numbers pollute RAG text and confuse chunking | Medium | Line break normalization | Detect repeating text at top/bottom across consecutive pages. Remove or tag as metadata. High value for RAG quality. |
| **Footnote separator detection** | Academic texts have footnotes that break text flow; separating body from notes enables proper RAG chunking | High | Line break normalization | Detect horizontal rules, superscript number patterns. Output footnotes as separate section or tagged blocks. Significant RAG value. |
| **MCP async job handling** | Long OCR jobs (multi-hundred-page books) block MCP tool calls; async pattern enables better UX | Medium | MCP server (exists) | Submit -> job ID -> poll status -> retrieve result. Standard long-running MCP tool pattern. |
| **Timeout handling per file** | One corrupt PDF hangs a Tesseract worker indefinitely, blocking the entire pipeline | Medium | Pipeline (exists) | Per-future timeout on `ProcessPoolExecutor`. Kill hung workers. Report as error, continue remaining files. Currently no timeout protection. |
| **Configurable post-processing pipeline** | Different downstream consumers want different normalizations; RAG wants dehyphenation, citation databases want original line breaks | Low | All post-processing features | Chain of transform functions, each toggleable via config/CLI. `--normalize dehyphenate,linebreaks,unicode` or `--raw` to skip. |
| **Per-page engine provenance in output** | Auditing which pages used which engine for quality tracking | Low | JSON metadata | Already tracked in `PageResult.engine`. Serialize to JSON. Minimal effort. |

## Anti-Features

Features to deliberately NOT build. Common mistakes in OCR post-processing that would harm the academic use case.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Spell-check correction of OCR output** | Academic texts contain intentional non-standard words: Dasein, aletheia, Erschlossenheit, epoche. Auto-correction would destroy content. The existing whitelist approach is the correct boundary. | Post-processing normalizes formatting (hyphens, line breaks, unicode), never content. Quality scoring detects problems; humans fix content. |
| **Automatic language detection per page** | Humanities texts mix languages within paragraphs (Greek quotes in English, German terms in French commentary). Per-page detection picks wrong primary language. | Keep user-specified language list applied to all pages. Multi-language Tesseract config handles mixed text correctly. |
| **PDF text layer replacement** | Replacing text layers in original PDF is fragile, breaks signatures, and most RAG consumers want plain text. | Output .txt and .json alongside original PDF. Copy original unchanged. |
| **Real-time streaming output** | Batch processing tool. WebSocket/SSE complexity for no real user benefit. | MCP async polling covers non-blocking use case. CLI progress bars exist. |
| **OCR model training/fine-tuning** | Different product entirely. Enormous complexity, minimal gain for pipeline tool. | Use pretrained models. Surya fallback handles Tesseract failures. |
| **Image preprocessing** | ocrmypdf handles deskew/denoise/binarize internally. Duplicating adds conflicts. | Let ocrmypdf preprocess. Focus on text post-processing. |
| **Markdown/EPUB export** | Scope creep. Plain text + JSON metadata covers RAG and programmatic use cases. Formatting is a downstream concern. | Output clean .txt. Let users pipe to pandoc or other tools for format conversion. |

## Feature Dependencies

```
Environment validation (startup, independent)
    |
    v
Pipeline execution (exists)
    |
    +-- Structured logging (wraps existing logging, independent)
    |
    +-- Timeout handling (wraps ProcessPoolExecutor, independent)
    |
    v
Text extraction (exists) --> Post-processing chain:
    |
    1. Unicode normalization (NFC) -- foundational, do first
    |
    2. Punctuation normalization -- depends on clean unicode
    |
    3. Line break normalization -- depends on clean unicode
    |
    4. Dehyphenation -- requires normalized line breaks
    |        |
    |        +-- [Optional] Language-aware dehyphenation (extends basic)
    |
    5. [Optional] Header/footer stripping
    |
    6. [Optional] Footnote detection
    |
    v
Output generation:
    .txt file (post-processed text)
    .json metadata (quality, engine, timing)
    .pdf (original, copied unchanged)
    |
    v
Work directory cleanup (after successful output)
    |
    v
MCP async jobs (wraps pipeline, independent)
```

## MVP Recommendation

For v2.0, prioritize in this order:

**Phase 1: Foundation (robustness)**
1. Environment validation -- prevents confusing errors, small effort
2. Structured logging -- QueueHandler pattern, improves debuggability
3. Work directory cleanup -- simple, immediate disk space benefit
4. Timeout handling -- production robustness, prevents hangs

**Phase 2: Post-processing pipeline**
5. Unicode normalization (NFC) -- foundational for all text cleanup
6. Line break normalization -- biggest single RAG readability improvement
7. Dehyphenation -- critical for search; academic texts heavily hyphenated
8. Punctuation normalization -- quick win once chain exists

**Phase 3: Output and integration**
9. JSON metadata output -- enables programmatic consumers
10. Configurable post-processing flags -- let users toggle normalizations
11. MCP async job handling -- non-blocking long jobs

**Defer to v3.0:**
- Header/footer stripping: needs heuristic tuning, medium complexity
- Footnote detection: high complexity, needs layout analysis research
- Language-aware dehyphenation: layer on top of basic dehyphenation later

## Implementation Notes

### Dehyphenation algorithm

```
1. Find pattern: word_fragment + hyphen + newline + next_word_start
2. Test join: concatenate fragments without hyphen
3. Validate: is joined form in dictionary? (use existing DictionarySignal)
4. If valid word: use joined form
5. If not valid: keep hyphen, replace newline with space
6. Special: soft hyphens (U+00AD) -> always remove
7. Special: preserve explicit compound hyphens (e.g., "well-known" not at line end)
```

### Line break normalization rules

```
- Single \n mid-sentence -> space (OCR layout break)
- \n after sentence-ending punctuation [.!?] + \n before capital -> paragraph break (\n\n)
- Blank line (\n\n+) -> single paragraph break (\n\n)
- \n after colon, next line indented -> preserve (block quote/list)
```

### Unicode normalization order

```python
import unicodedata

def normalize_unicode(text: str) -> str:
    text = unicodedata.normalize('NFC', text)
    # Ligature decomposition
    text = text.replace('\ufb01', 'fi').replace('\ufb02', 'fl')
    text = text.replace('\ufb03', 'ffi').replace('\ufb04', 'ffl')
    # Whitespace normalization
    text = text.replace('\u00a0', ' ')  # NBSP
    text = text.replace('\u200b', '')   # zero-width space
    text = text.replace('\ufeff', '')   # BOM/zero-width no-break
    return text
```

### Structured logging pattern

```python
# In main process
import logging.handlers, multiprocessing

log_queue = multiprocessing.Queue()
listener = logging.handlers.QueueListener(log_queue, *handlers)
listener.start()

# In worker processes
queue_handler = logging.handlers.QueueHandler(log_queue)
logger = logging.getLogger()
logger.addHandler(queue_handler)
```

## Sources

- Python `unicodedata` module documentation (HIGH confidence)
- Python `logging.handlers.QueueHandler` cookbook (HIGH confidence)
- OCR post-processing patterns from document digitization field -- dehyphenation, line normalization, NFC are standard across Apache Tika, ABBYY post-processing, Tesseract community scripts (MEDIUM confidence, domain knowledge)
- Codebase analysis of existing quality.py, pipeline.py, processor.py (HIGH confidence)
