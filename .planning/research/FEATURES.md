# Feature Landscape

**Domain:** Academic text OCR pipeline (Continental philosophy / humanities)
**Researched:** 2026-01-28
**Confidence:** MEDIUM (domain expertise, no web verification available)

## Table Stakes

Features users expect. Missing = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| PDF in, searchable PDF + plain text out | Basic OCR contract | Low | Already have |
| Multi-language support | Academic texts mix languages constantly | Med | Have: eng/fra/ell/lat. Need: deu (German is everywhere in philosophy) |
| Page-level quality scoring | Users need to know which pages are bad | Low | Already have (regex-based) |
| Batch processing with progress | Academics process whole book scans | Low | Already have (Rich UI) |
| Preserve original PDF if quality is good | Don't degrade already-OCR'd files | Low | Already have |
| Library/programmatic API | Any serious tool needs non-CLI usage | Med | **Missing.** CLI-only today. Blocks integration with other tools |
| Configurable quality threshold | Different scans need different sensitivity | Low | Already have |
| Idempotent re-runs | Don't re-process already-done files | Low | Partially have (existing text check) |
| Error recovery / partial results | Don't lose 99 files because file 100 failed | Low | Have (per-file error handling) |
| Structured result reporting | Programmatic access to what happened | Med | **Missing.** Results are printed, not returned cleanly |

## Differentiators

Features that set product apart. Not expected, but valued.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Hybrid OCR engine fallback** | Fast Tesseract first, expensive Surya only on failures — best quality-to-cost ratio | Med | Already have (core design) |
| **Multi-signal quality analysis** | Go beyond garbled text detection to catch layout errors, systematic misrecognitions, real-word substitutions | High | **Key gap.** See Quality Signals section below |
| **Academic term awareness** | Don't flag Erschlossenheit as garbled | Med | Already have (whitelist). Extend to configurable domain dictionaries |
| **Confidence-per-word from OCR engine** | Use Tesseract's native word confidence (hOCR output), not just post-hoc regex | Med | **High value, moderate effort.** Tesseract already computes this |
| **Layout-aware quality analysis** | Detect footnote/header confusion, column merge errors, table destruction | High | Differentiating for academic texts with complex layouts |
| **Dictionary-based validation** | Check words against language dictionaries to catch valid-looking but wrong words | Med | Hunspell/enchant integration. Catches "tlie" → "the" type errors |
| **Comparative scoring** | Run both engines, compare outputs, pick best per-page | Med | Expensive but highest quality. Could be opt-in "max quality" mode |
| **Export formats** | Markdown, structured JSON, EPUB beyond plain text | Med | Academics want different outputs for different workflows |
| **Reading order detection** | Correct column/footnote reading order in output | High | Surya/Marker may handle this; Tesseract often gets it wrong |
| **Configurable domain dictionaries** | Load discipline-specific term lists (philosophy, classics, theology) | Low | Extend current VALID_TERMS pattern |

## Anti-Features

Features to explicitly NOT build. Common mistakes in this domain.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **GUI / web interface** | Scope creep. Academics who scan books use CLI/scripts. GUI is a separate product | Invest in library API; let others build GUIs on top |
| **Training custom OCR models** | Enormous complexity, requires labeled data, diminishing returns vs. Surya | Use best available pretrained models (Tesseract, Surya). Focus on quality analysis and engine selection |
| **Real-time / streaming OCR** | Academic batch processing is inherently offline | Optimize batch throughput instead |
| **Cloud/API service** | Deployment complexity, data privacy concerns for unpublished manuscripts | Stay local-first. Desktop/server tool |
| **Image preprocessing (deskew, denoise, binarize)** | ocrmypdf already handles this well internally | Let ocrmypdf do preprocessing. Don't duplicate |
| **Full document structure extraction (TOC, chapters, semantic sections)** | Massive scope. Different problem than OCR quality | Output clean text; let downstream tools (e.g., LLMs) handle structure |
| **Handwriting recognition** | Different technology entirely. Printed academic texts are the domain | Document as out of scope |

## Quality Signals: Deep Dive

The core research question. Current system uses only regex garbled text detection. Here are quality signals ordered by value/complexity ratio:

### Tier 1: High Value, Low-Medium Complexity

**1. OCR Engine Confidence Scores**
- Tesseract outputs per-word confidence via hOCR/ALTO XML
- ocrmypdf can preserve this (`--output-type pdfa` with sidecar)
- Signal: Mean word confidence, % of words below threshold (e.g., <60%)
- **Recommendation: Implement first.** Highest signal-to-effort ratio
- Dependency: Need to extract hOCR from Tesseract output, or use `--sidecar` with ocrmypdf

**2. Dictionary Lookup**
- Check extracted words against Hunspell dictionaries (multi-language)
- Signal: % of words not found in any configured dictionary
- Catches real-word substitutions regex misses ("tlie" for "the", "liave" for "have")
- Libraries: `pyenchant` or `hunspell` Python bindings
- **Recommendation: Implement second.** Complements confidence scores
- Dependency: Language detection per page (or use configured languages)

**3. Character-Level Statistics**
- Ratio of alphabetic to non-alphabetic characters
- Already partially implemented (alpha_ratio check)
- Add: unusual character frequency distribution (too many rare chars = garbled)
- Add: unexpected Unicode blocks for declared language
- **Recommendation: Extend existing implementation**
- Dependency: None

### Tier 2: Medium Value, Medium Complexity

**4. N-gram / Language Model Perplexity**
- Run extracted text through a small language model
- High perplexity = text doesn't read like natural language
- Can use lightweight models (KenLM, or character-level n-grams)
- Catches subtler errors that pass dictionary checks
- **Recommendation: Consider for v2.** Adds dependency complexity
- Dependency: Language models per supported language

**5. Layout Consistency Checks**
- Compare line lengths across a page (sudden changes = column merge)
- Check for repeated headers/footers appearing mid-text
- Detect text that jumps between unrelated topics (paragraph coherence)
- Signal: Standard deviation of line lengths, duplicate text blocks
- **Recommendation: Implement selectively.** Line-length variance is easy; coherence is hard
- Dependency: Page layout information from PDF

**6. Cross-Engine Agreement**
- Run both Tesseract and Surya, compare outputs
- High agreement = both probably right; disagreement = uncertain
- Can use at word level (Levenshtein distance between outputs)
- **Recommendation: Expensive but excellent for "max quality" mode**
- Dependency: Both engines available

### Tier 3: High Value but High Complexity

**7. Reference/Citation Validation**
- Academic texts have predictable citation patterns
- Check that page references, footnote numbers, bibliographic entries parse correctly
- Signal: % of detected citations that parse vs. garbled
- **Recommendation: Defer.** Very domain-specific regex work
- Dependency: Citation pattern library

**8. Visual-Textual Comparison (rendered vs. source)**
- Render OCR text back to image, compare with source scan
- Pixel-level or SSIM comparison
- Gold standard for OCR quality but very expensive
- **Recommendation: Anti-feature for this project.** Research tool, not production tool
- Dependency: Rendering pipeline, image comparison

### Composite Quality Score

Current: `score = 1.0 - (garbled_ratio * 2)`

Recommended composite (weighted signals):
```
quality = w1 * engine_confidence    # 0.35 weight
        + w2 * dictionary_hit_rate  # 0.30 weight
        + w3 * (1 - garbled_ratio)  # 0.20 weight (current approach)
        + w4 * layout_consistency   # 0.15 weight
```

This is more robust than any single signal. Each catches different failure modes:
- Engine confidence: catches uncertain characters
- Dictionary: catches real-word substitutions
- Garbled regex: catches catastrophic failures
- Layout: catches structural errors

## Feature Dependencies

```
Library API ← (no dependencies, enables everything)
  ↓
Structured Results ← Library API
  ↓
Multi-signal Quality ← Library API
  ├── Engine Confidence ← hOCR extraction from Tesseract
  ├── Dictionary Validation ← pyenchant/hunspell + language config
  ├── Character Statistics ← (extend existing)
  └── Layout Checks ← PDF layout extraction
  ↓
Configurable Domain Dicts ← Dictionary Validation
  ↓
Comparative Scoring ← Multi-signal Quality + both engines
```

Key ordering constraint: Library API must come first because it forces clean interfaces that all other features build on.

## MVP Recommendation

For the rearchitecture milestone, prioritize:

1. **Library API** (table stakes, unblocks everything)
2. **Structured result reporting** (table stakes, needed for testing)
3. **Engine confidence scores** (highest-value quality signal, moderate effort)
4. **Dictionary-based validation** (second-highest-value quality signal)
5. **Configurable domain dictionaries** (extends existing whitelist pattern)
6. **German language support** (missing table stakes for philosophy texts)

Defer to post-milestone:
- N-gram perplexity: Adds model dependencies, moderate value over dictionary checks
- Layout consistency: Complex, benefits fewer documents
- Comparative scoring: Expensive, better as opt-in later
- Export formats: Useful but not core quality improvement

## Sources

- Domain expertise in OCR quality assessment (MEDIUM confidence — no web verification available)
- Codebase analysis of current quality.py implementation (HIGH confidence)
- Tesseract documentation knowledge re: hOCR confidence output (MEDIUM confidence — not verified against current version)
- ocrmypdf capabilities for sidecar text and confidence (MEDIUM confidence)
