---
name: ocr-debug
description: Debug OCR quality issues for specific PDFs or pages
disable-model-invocation: true
---

# OCR Debug Skill

Help diagnose OCR quality issues in the scholardoc-ocr pipeline.

## When invoked

The user will describe an OCR quality problem (garbled output, wrong language detection, pages unnecessarily sent to Surya, etc.).

## Diagnostic Steps

1. **Identify the module**: Determine if the issue is in Tesseract output (processor.py), quality scoring (quality.py), or pipeline routing (pipeline.py)
2. **Check quality thresholds**: Read the QualityAnalyzer logic and the current threshold. Determine if the threshold is too aggressive or too lenient for the described case
3. **Check whitelist coverage**: If valid terms are being flagged as garbled, check if they need to be added to the academic term whitelist in quality.py
4. **Check language config**: Verify the Tesseract and Surya language lists match the document's languages
5. **Suggest fixes**: Propose specific code changes, threshold adjustments, or whitelist additions

## Key files to read
- `src/scholardoc_ocr/quality.py` — scoring logic and whitelist
- `src/scholardoc_ocr/processor.py` — OCR invocation parameters
- `src/scholardoc_ocr/pipeline.py` — phase 1/phase 2 routing logic
