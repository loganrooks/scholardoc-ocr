# ScholarDoc OCR

High-performance OCR pipeline for academic texts, optimized for Apple Silicon.

## Features

- **Hybrid OCR**: Fast Tesseract first pass, Surya/Marker for problem pages
- **Page-level quality analysis**: Flags only pages that need reprocessing
- **Multilingual**: English, French, Greek, Latin support
- **Parallel processing**: File-level and within-file parallelization
- **Smart filtering**: Recognizes academic references, philosophical terms

## Installation

```bash
pip install -e .
```

## Usage

```bash
# Process all PDFs in a folder
ocr ~/Documents/scans

# Custom output directory
ocr ~/Downloads -o ./output

# Higher quality threshold (more pages sent to Surya)
ocr --quality 0.9 ~/scans

# Force Tesseract re-OCR on all files
ocr --force ~/scans

# Debug mode with sample problem text
ocr --debug ~/scans

# Process specific files
ocr -f file1.pdf file2.pdf
```

## Output

For each input PDF, produces:
- `filename.pdf` - Searchable PDF with text layer
- `filename.txt` - Extracted plain text

## Requirements

- Python 3.11-3.13
- Tesseract OCR with language packs
- Apple Silicon recommended for Surya acceleration
