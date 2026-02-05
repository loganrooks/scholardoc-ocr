# Phase 14: Cross-File Batching - Research

**Researched:** 2026-02-04
**Domain:** GPU batch processing, Surya/Marker OCR configuration, memory-aware batch sizing
**Confidence:** HIGH

## Summary

This research addresses how to implement cross-file page batching for Surya OCR processing. The current pipeline processes files sequentially in Phase 2 (Surya), resulting in 5 files with 10 flagged pages each producing 5 separate Surya calls rather than 1 optimized batch of 50 pages. Cross-file batching aggregates all flagged pages into a single Surya conversion, maximizing GPU utilization.

The key insight is that Surya/Marker batch sizes are controlled via **environment variables** (`RECOGNITION_BATCH_SIZE`, `DETECTOR_BATCH_SIZE`, `LAYOUT_BATCH_SIZE`, `TABLE_REC_BATCH_SIZE`), not programmatically via the `PdfConverter` config. The batch_size field in `SuryaConfig` is currently unused. Hardware-aware defaults should consider MPS unified memory constraints, where aggressive batch sizes cause system-wide slowdown rather than clean OOM errors.

**Primary recommendation:** Aggregate flagged pages across files into a temporary combined PDF, process with single Surya call, then map results back to source files using page-to-file tracking. Set batch size environment variables before model import based on available system memory.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| marker-pdf | >=1.0.0 | PDF-to-markdown OCR | Already in use, provides PdfConverter with page_range support |
| PyMuPDF (fitz) | >=1.24.0 | PDF manipulation | Already in use for page extraction/replacement |
| psutil | >=5.0.0 | System memory detection | Cross-platform memory queries for adaptive batch sizing |
| torch | >=2.0.0 | MPS/CUDA memory APIs | GPU memory tracking for adaptive sizing |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| cachetools | >=5.0.0 | TTLCache | Already in use for model caching (Phase 13) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Combined PDF approach | Image list extraction | Marker only accepts PDF paths, not PIL images directly |
| Environment variables | Config JSON | Env vars are Surya's documented approach; config JSON requires file I/O |

**Installation:**
```bash
# psutil already available in Python stdlib-adjacent
pip install psutil  # If not already present
```

## Architecture Patterns

### Recommended Project Structure
```
src/scholardoc_ocr/
    batch.py           # New: Cross-file batch aggregation
    surya.py           # Modified: Env var configuration
    pipeline.py        # Modified: Single Surya call pattern
    model_cache.py     # Existing: Model caching (Phase 13)
```

### Pattern 1: Page Aggregation with Origin Tracking
**What:** Collect all flagged pages across files into a data structure that tracks source file and page number, create temporary combined PDF, process in single batch.
**When to use:** Always for cross-file batching.
**Example:**
```python
# Source: Prior research in FEATURES.md
from dataclasses import dataclass
from pathlib import Path

@dataclass
class FlaggedPage:
    """Track origin of a flagged page for result mapping."""
    file_result: FileResult
    page_number: int
    input_path: Path
    batch_index: int  # Position in combined PDF

def collect_flagged_pages(
    file_results: list[FileResult],
    input_dir: Path,
) -> list[FlaggedPage]:
    """Aggregate flagged pages from all files."""
    pages = []
    for fr in file_results:
        input_path = input_dir / fr.filename
        for page in fr.flagged_pages:
            pages.append(FlaggedPage(
                file_result=fr,
                page_number=page.page_number,
                input_path=input_path,
                batch_index=len(pages),
            ))
    return pages
```

### Pattern 2: Environment Variable Configuration Before Import
**What:** Set Surya batch size environment variables before importing marker modules, since Surya reads them at import time via pydantic-settings.
**When to use:** Before any marker/surya imports, ideally at pipeline start.
**Example:**
```python
# Source: Surya GitHub README, verified via WebSearch
import os

def configure_surya_batch_sizes(
    device: str,
    available_memory_gb: float,
) -> dict[str, str]:
    """Set Surya env vars based on device and available memory.

    Returns dict of set env vars for logging.
    """
    if device in ("mps", "cuda"):
        if available_memory_gb >= 32:
            os.environ.setdefault("RECOGNITION_BATCH_SIZE", "128")
            os.environ.setdefault("DETECTOR_BATCH_SIZE", "64")
        elif available_memory_gb >= 16:
            os.environ.setdefault("RECOGNITION_BATCH_SIZE", "64")
            os.environ.setdefault("DETECTOR_BATCH_SIZE", "32")
        else:  # 8GB
            os.environ.setdefault("RECOGNITION_BATCH_SIZE", "32")
            os.environ.setdefault("DETECTOR_BATCH_SIZE", "16")
    else:  # CPU
        os.environ.setdefault("RECOGNITION_BATCH_SIZE", "32")
        os.environ.setdefault("DETECTOR_BATCH_SIZE", "6")

    return {
        "RECOGNITION_BATCH_SIZE": os.environ.get("RECOGNITION_BATCH_SIZE"),
        "DETECTOR_BATCH_SIZE": os.environ.get("DETECTOR_BATCH_SIZE"),
    }
```

### Pattern 3: Memory-Aware Default Calculation
**What:** Detect system memory at runtime to select appropriate batch sizes.
**When to use:** At pipeline initialization, before model loading.
**Example:**
```python
# Source: psutil documentation, PyTorch MPS docs
import psutil

def get_available_memory_gb() -> float:
    """Get available GPU/unified memory in GB."""
    try:
        import torch
        if torch.backends.mps.is_available():
            # MPS uses unified memory - use system total
            return psutil.virtual_memory().total / (1024**3)
        elif torch.cuda.is_available():
            # CUDA has dedicated VRAM
            props = torch.cuda.get_device_properties(0)
            return props.total_memory / (1024**3)
    except ImportError:
        pass
    # Fallback to system memory
    return psutil.virtual_memory().total / (1024**3)
```

### Pattern 4: Combined PDF Creation
**What:** Use PyMuPDF to create temporary PDF with all flagged pages.
**When to use:** When preparing batch for Surya.
**Example:**
```python
# Source: Existing processor.py patterns
from pathlib import Path
import fitz

def create_combined_pdf(
    flagged_pages: list[FlaggedPage],
    output_path: Path,
) -> bool:
    """Create single PDF containing all flagged pages."""
    result_doc = fitz.open()

    for page in flagged_pages:
        with fitz.open(page.input_path) as source:
            result_doc.insert_pdf(
                source,
                from_page=page.page_number,
                to_page=page.page_number,
            )

    result_doc.save(output_path)
    result_doc.close()
    return True
```

### Anti-Patterns to Avoid
- **Dynamic batch size changes mid-job:** Surya batch sizes are set at import time. Changing requires process restart or very careful module reloading.
- **Multiprocessing for Surya:** MPS/CUDA cannot share GPU tensors across processes. Use batching for parallelism, not multiprocessing.
- **Aggressive memory cleanup between pages:** `torch.mps.empty_cache()` per page adds overhead. Cleanup only between documents.
- **Copying CUDA batch sizes for MPS:** CUDA recommendations (RECOGNITION_BATCH_SIZE=864) cause system freezes on MPS unified memory.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PDF page extraction | Custom PyPDF2 code | PyMuPDF `insert_pdf` | Already in codebase, handles edge cases |
| Memory detection | /proc/meminfo parsing | `psutil.virtual_memory()` | Cross-platform, handles MPS unified memory |
| GPU memory stats | nvidia-smi parsing | `torch.cuda.memory_allocated()` / `torch.mps.current_allocated_memory()` | Official PyTorch APIs |
| Batch size calculation | Fixed values per device | Memory-aware calculation | 8GB vs 96GB machines need different defaults |

**Key insight:** Surya's batch size configuration is via environment variables read at import time. There is no runtime API to change batch sizes without module reloading.

## Common Pitfalls

### Pitfall 1: Setting Env Vars After Marker Import
**What goes wrong:** Environment variables set after `from marker.converters.pdf import PdfConverter` have no effect - Surya already read them.
**Why it happens:** Surya uses pydantic-settings which reads env vars at import time.
**How to avoid:** Configure env vars at the very start of pipeline, before any marker/surya imports.
**Warning signs:** Batch sizes in logs don't match env vars you set.

### Pitfall 2: MPS Unified Memory Exhaustion Without OOM
**What goes wrong:** System becomes unresponsive, beach-balls, no Python error. macOS tries to swap GPU memory before failing.
**Why it happens:** MPS unified memory shares with CPU. Aggressive batch sizes consume all memory gradually.
**How to avoid:** Conservative MPS batch sizes (see pattern 2). Test on 8GB machines.
**Warning signs:** Activity Monitor shows yellow/red memory pressure during OCR.

### Pitfall 3: Result Mapping Off-By-One
**What goes wrong:** Surya results mapped to wrong source file or page.
**Why it happens:** Combined PDF page indices don't match `batch_index` tracking.
**How to avoid:** Verify batch_index assignment matches `insert_pdf` order. Add assertion tests.
**Warning signs:** OCR text appears in wrong file's output.

### Pitfall 4: Ignoring Page Range in Existing convert_pdf
**What goes wrong:** Surya processes entire combined PDF instead of just the requested pages.
**Why it happens:** `page_range` parameter in converter_config not passed.
**How to avoid:** Always pass page_range when processing combined PDF (or omit if processing all).
**Warning signs:** Processing time much longer than expected for batch size.

### Pitfall 5: Memory Pressure Detection Too Late
**What goes wrong:** Adaptive batch sizing detects OOM after job fails.
**Why it happens:** Checking memory after allocation, not before.
**How to avoid:** Monitor `torch.mps.current_allocated_memory()` / `torch.cuda.memory_allocated()` BEFORE batch, reduce proactively.
**Warning signs:** OOM on second/third batch of large jobs.

## Code Examples

Verified patterns from official sources:

### Surya Environment Variables
```python
# Source: https://github.com/datalab-to/surya README
# Memory per batch item (VRAM/unified memory):
#   RECOGNITION_BATCH_SIZE: ~40MB per item (was 50MB, updated defaults)
#   DETECTOR_BATCH_SIZE: ~440MB per item (was 280MB, updated)
#   LAYOUT_BATCH_SIZE: ~220MB per item
#   TABLE_REC_BATCH_SIZE: ~150MB per item

# GPU defaults (Surya v0.8+):
#   RECOGNITION_BATCH_SIZE=512 (~20GB VRAM)
#   DETECTOR_BATCH_SIZE=36 (~16GB VRAM)

# CPU defaults:
#   RECOGNITION_BATCH_SIZE=32
#   DETECTOR_BATCH_SIZE=6

# MPS conservative (8GB unified):
os.environ["RECOGNITION_BATCH_SIZE"] = "32"
os.environ["DETECTOR_BATCH_SIZE"] = "16"

# MPS moderate (16GB unified):
os.environ["RECOGNITION_BATCH_SIZE"] = "64"
os.environ["DETECTOR_BATCH_SIZE"] = "32"

# MPS aggressive (32GB+ unified):
os.environ["RECOGNITION_BATCH_SIZE"] = "128"
os.environ["DETECTOR_BATCH_SIZE"] = "64"
```

### System Memory Detection
```python
# Source: psutil documentation
import psutil

mem = psutil.virtual_memory()
total_gb = mem.total / (1024**3)
available_gb = mem.available / (1024**3)

# For MPS: total unified memory is what matters
# For CUDA: use torch.cuda.get_device_properties(0).total_memory
```

### GPU Memory Monitoring
```python
# Source: PyTorch documentation
import torch

def get_gpu_memory_mb() -> tuple[float, float]:
    """Return (allocated_mb, available_mb) for GPU."""
    if torch.backends.mps.is_available():
        allocated = torch.mps.current_allocated_memory() / (1024**2)
        # MPS doesn't have reserved/available API
        # Use system memory as proxy
        import psutil
        available = psutil.virtual_memory().available / (1024**2)
        return allocated, available
    elif torch.cuda.is_available():
        allocated = torch.cuda.memory_allocated() / (1024**2)
        reserved = torch.cuda.memory_reserved() / (1024**2)
        props = torch.cuda.get_device_properties(0)
        total = props.total_memory / (1024**2)
        return allocated, total - reserved
    return 0.0, 0.0
```

### Adaptive Batch Sizing
```python
# Source: Research synthesis from PITFALLS.md, FEATURES.md
def compute_batch_size(
    total_pages: int,
    available_memory_gb: float,
    device: str,
) -> int:
    """Compute appropriate batch size for workload.

    Args:
        total_pages: Number of flagged pages to process.
        available_memory_gb: Available GPU/unified memory.
        device: "mps", "cuda", or "cpu".

    Returns:
        Recommended batch size (pages per Surya call).
    """
    # Memory per page estimates (conservative)
    # Detection: ~440MB, Recognition: ~40MB, Layout: ~220MB
    # Total: ~700MB per page at peak
    memory_per_page_gb = 0.7

    if device == "cpu":
        # CPU is memory-limited by different factors
        return min(total_pages, 32)

    # GPU: use 50% of available for safety margin
    safe_memory = available_memory_gb * 0.5
    max_by_memory = int(safe_memory / memory_per_page_gb)

    # Clamp to reasonable range
    return max(1, min(total_pages, max_by_memory, 100))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Fixed batch_size=50 in SuryaConfig | Environment variables | marker-pdf 1.0+ | Must use env vars, config field ignored |
| Per-file Surya calls | Cross-file batching | Best practice | 2-3x speedup for multi-file jobs |
| CUDA-sized batches on MPS | Memory-aware MPS defaults | 2024+ | Prevents system freezes |
| Process-level parallelism | Batch-level parallelism | N/A | MPS/CUDA don't support multiprocess GPU sharing |

**Deprecated/outdated:**
- `SuryaConfig.batch_size`: Exists but not passed to converter. Use `RECOGNITION_BATCH_SIZE` env var instead.
- CUDA batch size recommendations for MPS: 864 recognition batch causes MPS memory pressure.

## Open Questions

Things that couldn't be fully resolved:

1. **Adaptive batch sizing during processing**
   - What we know: Can monitor `torch.mps.current_allocated_memory()` during processing.
   - What's unclear: Whether Surya supports mid-batch size changes without converter recreation.
   - Recommendation: Implement conservative upfront sizing first. Defer mid-batch adaptation to later phase if needed.

2. **Marker's internal batch handling**
   - What we know: Marker batches internally based on env vars.
   - What's unclear: Whether page_range affects internal batching or just which pages to output.
   - Recommendation: Test with combined PDF to verify behavior. May need to process all pages and filter output.

3. **Result text extraction from combined PDF**
   - What we know: Marker returns single markdown string for entire PDF.
   - What's unclear: How to reliably split result back to individual pages.
   - Recommendation: Use page separators in markdown output, or process page-by-page within combined PDF using page_range.

## Sources

### Primary (HIGH confidence)
- [Surya GitHub](https://github.com/datalab-to/surya) - RECOGNITION_BATCH_SIZE, DETECTOR_BATCH_SIZE defaults and memory requirements
- [marker-pdf PyPI](https://pypi.org/project/marker-pdf/) - Current version 1.10.2, PdfConverter configuration
- [PyTorch MPS documentation](https://docs.pytorch.org/docs/stable/mps.html) - MPS memory APIs
- [psutil documentation](https://psutil.readthedocs.io/) - virtual_memory() for system RAM
- Existing codebase: `surya.py`, `pipeline.py`, `processor.py`, `model_cache.py`

### Secondary (MEDIUM confidence)
- [Marker Issue #443](https://github.com/VikParuchuri/marker/issues/443) - Batch size configuration via JSON config
- [Surya Issue #183](https://github.com/VikParuchuri/surya/issues/183) - Running on lower VRAM GPUs
- Prior research: `.planning/research/FEATURES.md`, `PITFALLS.md`, `STACK.md`

### Tertiary (LOW confidence)
- WebSearch: "marker-pdf batch size configuration 2026" - Multiple sources agree on env var approach
- WebSearch: "PyTorch MPS memory management adaptive batch sizing" - Community patterns

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Using existing dependencies (marker-pdf, PyMuPDF, psutil)
- Architecture: HIGH - Patterns derived from existing codebase and official docs
- Pitfalls: HIGH - Well-documented in prior research and Surya issues
- Batch sizing defaults: MEDIUM - Memory-per-item varies by version, needs validation

**Research date:** 2026-02-04
**Valid until:** 2026-03-04 (30 days - Surya/Marker versioning is stable)
