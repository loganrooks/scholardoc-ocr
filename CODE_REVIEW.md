# Code Review — scholardoc-ocr

## CRITICAL: Phase 2 Surya results are never written back

`pipeline.py:552-567` — After Surya processes bad pages, the code maps text back to files in `texts_by_file`, but **never actually updates the text files**. The loop at line 564 checks if the text file exists and prints a log message, but doesn't write anything:

```python
for filename, page_data in texts_by_file.items():
    text_path = config.output_dir / "final" / f"{Path(filename).stem}.txt"
    if text_path.exists():
        console.print(f"    [dim]{filename}: {len(page_data)} pages enhanced[/dim]")
        # ← nothing is written!
```

The entire Phase 2 is effectively a no-op. You need to read the existing text, replace the bad pages with Surya text, and write it back. Same issue for the PDF — the Surya-OCR'd pages are never spliced back into the output PDF.

## CRITICAL: `run_surya_batch` discards Surya output

`processor.py:309-317` — After running Surya via `converter(str(batch_pdf))`, the rendered markdown (`rendered.markdown`) is **discarded**. Instead, `extract_text_by_page(batch_pdf)` re-extracts text from the same input PDF that was already known to be bad. Surya's converter doesn't modify the PDF in-place — it returns rendered output. The text extraction reads the original (pre-Surya) embedded text layer:

```python
rendered = converter(str(batch_pdf))          # Surya result in rendered.markdown
batch_page_texts = self.extract_text_by_page(batch_pdf)  # ← reads ORIGINAL bad text!
```

You need to parse `rendered.markdown` to get per-page text, or use Surya's page-level output if available.

## HIGH: Resource leak — fitz documents not closed on exceptions

`processor.py:60-66, 68-77, 79-95, 97-129, 131-139, 229-240` — Every `fitz.open()` call uses manual `.close()` but no `try/finally` or context manager. If an exception occurs between open and close, the file handle leaks. PyMuPDF documents support context managers:

```python
# Current (leaks on exception):
doc = self.fitz.open(pdf_path)
texts = [page.get_text() for page in doc]
doc.close()

# Should be:
with self.fitz.open(pdf_path) as doc:
    texts = [page.get_text() for page in doc]
```

This applies to **every** method in `PDFProcessor`.

## HIGH: `combine_pages_from_multiple_pdfs` opens/closes a document per page

`processor.py:232-235` — Each `(pdf_path, page_num)` tuple opens the entire PDF, inserts one page, then closes it. If you have 200 bad pages from 5 files, this opens the same PDF dozens of times. Group by file first:

```python
from itertools import groupby
for pdf_path, specs in groupby(sorted(page_specs, key=lambda s: s[0]), key=lambda s: s[0]):
    with self.fitz.open(pdf_path) as doc:
        for _, page_num in specs:
            combined.insert_pdf(doc, from_page=page_num, to_page=page_num)
```

## HIGH: Parallelization concern — CPU oversubscription

`pipeline.py:59` computes `jobs_per_file = max_workers // num_files`, then passes that to Tesseract's `--jobs` flag. But `ProcessPoolExecutor` also has `max_workers=8` (line 390), so you can have **8 processes x 2 threads each = 16 concurrent threads**. The pool worker count and per-file job count should be coordinated:

```python
# Should be: pool_workers * jobs_per_file <= total_cores
pool_workers = min(config.max_workers, len(input_files))
jobs_per_file = max(1, config.max_workers // pool_workers)
```

Currently you can massively oversubscribe the CPU.

## MEDIUM: `replace_pages` uses linear scan for page lookup

`processor.py:114` — `if page_num in page_numbers` does a linear scan of a list for every page. Convert to a `set` for O(1) lookup:

```python
page_set = set(page_numbers)
for page_num in range(len(original)):
    if page_num in page_set and replacement_idx < len(replacement):
```

## MEDIUM: Type annotation for `progress_callback`

`processor.py:250` — `callable` (lowercase) is not a valid type annotation in Python 3.11. Use `Callable` from `typing` or `collections.abc`:

```python
from collections.abc import Callable
progress_callback: Callable[[str, int, int], None] | None = None
```

## MEDIUM: Duplicate imports inside function body

`pipeline.py:362-363` — `from rich.live import Live` and `from rich.table import Table` are imported mid-function, but `Table` is already imported at module level (line 15). The `Live` import should be at the top of the file. Same issue at lines 512-513.

## LOW: Hardcoded "LEVINAS" in output

`pipeline.py:323` — The header says `LEVINAS OCR PIPELINE` but the project was renamed to `scholardoc-ocr` for general use. This is a leftover from the original project.

## LOW: Default `output_dir` in `PipelineConfig` is stale

`pipeline.py:29` — Default is `Path.home() / "Downloads" / "levinas_ocr"`, another leftover. The CLI overrides this, but the default in the dataclass is misleading.

## LOW: `recursive` mode only uses filenames, loses subdirectory paths

`cli.py:106` — `rglob("*.pdf")` returns full paths, but `.name` strips the directory. If two subdirectories contain `paper.pdf`, only one will be processed. The pipeline then looks up `config.input_dir / filename` which won't find files in subdirectories.

## LOW: `run_surya_on_pages` is dead code

`processor.py:335-383` — This method is never called anywhere. It also loads Surya models independently (no sharing with `run_surya_batch`), so if it were ever called it would be inefficient.

## Summary

| Priority | Issue |
|----------|-------|
| **CRITICAL** | Phase 2 results never written back to output files |
| **CRITICAL** | `run_surya_batch` discards Surya output, re-reads bad input text |
| **HIGH** | All fitz documents leak on exceptions (no context managers) |
| **HIGH** | `combine_pages_from_multiple_pdfs` reopens same PDFs repeatedly |
| **HIGH** | CPU oversubscription: pool workers x jobs_per_file > total cores |
| MEDIUM | `replace_pages` linear scan, wrong `callable` annotation, duplicate imports |
| LOW | Hardcoded "LEVINAS", stale default path, broken recursive mode, dead code |
