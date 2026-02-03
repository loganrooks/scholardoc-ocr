# Feature Landscape: PyTorch/Surya Performance Optimization

**Domain:** OCR pipeline GPU performance optimization (Apple Silicon / MPS)
**Researched:** 2026-02-03
**Confidence:** MEDIUM-HIGH (official Surya/Marker documentation, PyTorch MPS documentation; Apple Silicon ML patterns well-documented)

## Scope

This document focuses on performance optimization features for the Surya/Marker OCR backend on Apple Silicon. The current implementation is "insanely slow" despite MPS availability because:

1. **No explicit MPS device selection** - Marker auto-detects but may not optimize
2. **No cross-file batching** - 3 files with 10 flagged pages each = 3 jobs, not 1 batch of 30
3. **batch_size=50 configured but not passed to converter** - SuryaConfig has it, convert_pdf ignores it
4. **Per-file sequential Surya** - Files processed one at a time after Tesseract phase

## Current Implementation Analysis

From codebase review:

```python
# surya.py line 29 - SuryaConfig has batch_size
batch_size: int = 50  # <- configured but never used

# surya.py line 74 - load_models() uses default device
model_dict = create_model_dict()  # <- no explicit device

# surya.py line 117-120 - convert_pdf ignores batch_size
converter_config = {
    "languages": config.langs.split(","),
    "force_ocr": config.force_ocr,
    # batch_size NOT passed!
}

# pipeline.py line 378-453 - Per-file sequential Surya
for file_result in flagged_results:  # <- sequential, not batched
    surya_markdown = surya.convert_pdf(...)
```

## Table Stakes

Features users expect for GPU-accelerated OCR. Missing any means performance is unacceptably slow.

| Feature | Why Expected | Complexity | Depends On | Notes |
|---------|--------------|------------|------------|-------|
| **Explicit MPS device selection** | PyTorch auto-detection works but explicit `torch.device("mps")` ensures correct GPU usage and clearer error messages | Low | PyTorch >= 2.0 | Modify `load_models()` to detect MPS availability and pass explicit device. Check `torch.backends.mps.is_available()`. |
| **Pass batch_size to Marker converter** | Surya's RECOGNITION_BATCH_SIZE and DETECTOR_BATCH_SIZE dramatically affect performance. Config exists but isn't used. | Low | SuryaConfig (exists) | Set env vars `RECOGNITION_BATCH_SIZE`, `DETECTOR_BATCH_SIZE` before converter initialization. Default GPU batch: recognition=256, detection=36. |
| **VRAM-aware batch sizing** | Fixed batch size causes OOM on smaller GPUs or wastes capacity on larger. MPS unified memory behaves differently than discrete VRAM. | Medium | MPS device selection | Apple Silicon: unified memory means larger batches possible. M1: ~16GB, M2 Pro/Max: ~32-96GB. Auto-tune based on detected chip. |
| **Model warm-up on first load** | First inference is 2-5x slower due to kernel compilation. Warm-up hidden during "loading models" phase. | Low | Model loading (exists) | Run single dummy page through converter after load_models(). Amortizes compilation cost. |
| **Cross-file page batching** | Current: 3 files x 10 pages = 3 separate Surya jobs. Optimal: 1 batch of 30 pages, mapped back to files. Surya processes batches faster than sequential. | High | Pipeline restructure | Collect all flagged pages across files, create single batch, distribute results back. Major pipeline change. |

## Differentiators

Features beyond baseline that provide exceptional performance for academic document workloads.

| Feature | Value Proposition | Complexity | Depends On | Notes |
|---------|-------------------|------------|------------|-------|
| **Surya model compilation** | `COMPILE_DETECTOR=true`, `COMPILE_LAYOUT=true` enable torch.compile for 20-40% speedup after warm-up. MPS support is experimental but improving. | Medium | Model warm-up, PyTorch 2.0+ | Set env vars before import. Increases cold start time significantly (30-60s) but amortizes over large batches. Only worthwhile for 50+ page jobs. |
| **Memory pool optimization** | Reduce fragmentation by setting `PYTORCH_MPS_ALLOC_CONF` or reusing tensor allocations across pages. | Medium | MPS device selection | MPS memory management differs from CUDA. May need `torch.mps.empty_cache()` between large batches. Monitor with `torch.mps.current_allocated_memory()`. |
| **Adaptive batch sizing based on page complexity** | Dense text pages need more VRAM per item than sparse pages. Size batches dynamically. | High | VRAM monitoring | Estimate page complexity from image size / text density. Adjust batch size per iteration. Complex but prevents OOM on mixed documents. |
| **Progressive result streaming** | Return Surya results as pages complete rather than waiting for entire batch. Enables early partial results for MCP consumers. | Medium | Callback system (exists), Cross-file batching | Marker's internal architecture may not support this easily. Would require forking or custom converter wrapper. |
| **Model unloading after Surya phase** | Surya models consume ~5GB VRAM at peak. Explicit unload after Phase 2 frees memory for subsequent operations. | Low | Model loading | Call `del model_dict; torch.mps.empty_cache()` after Surya phase. Helps with multi-pipeline scenarios. |
| **Parallel Tesseract + Surya preparation** | While Tesseract runs on CPU, pre-load Surya models on GPU. Models ready when Phase 2 starts. | Medium | Pipeline restructure | Background thread for model loading during Phase 1. Reduces perceived wait time by 10-20s. |

## Anti-Features

Features to deliberately NOT build. Common performance optimization mistakes.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **torch.compile on MPS for all runs** | Compilation takes 30-60s. For typical 5-20 page academic PDFs, compilation overhead exceeds runtime savings. Only beneficial for 100+ page batches. | Enable via env var for power users. Default OFF. Document when worthwhile. |
| **Multiprocessing for Surya** | MPS (and CUDA) cannot share GPU tensors across processes via multiprocessing. Marker explicitly errors on MPS + multiprocessing. | Single-process Surya with larger batches. Parallelism comes from batching, not processes. |
| **Dynamic batch size changes mid-job** | Surya/Marker batch size is set at converter initialization, not per-page. Changing requires new converter instance with full model reload. | Set batch size once based on total flagged pages. Optimize for the full job, not individual files. |
| **CPU fallback for "small" jobs** | CPU is 10-50x slower than MPS for Surya inference. Even 2-page jobs benefit from GPU. Auto-CPU fallback wastes user time. | Always use MPS when available. Only fallback to CPU if MPS unavailable or explicitly requested. |
| **Aggressive memory cleanup between pages** | `torch.mps.empty_cache()` between every page adds overhead. Memory allocator is efficient at reuse. | Cleanup only between files or when approaching memory limits. Let allocator manage normal operations. |
| **Custom CUDA kernels** | Surya/Marker are pure PyTorch. Custom kernels add maintenance burden, break on updates, don't work on MPS. | Use upstream Marker. Contribute performance fixes if found. |

## Feature Dependencies

```
MPS Device Detection (foundation)
    |
    +-- Explicit device selection in load_models()
    |
    +-- VRAM detection for batch sizing
    |
    v
Environment Variable Configuration (before model import)
    |
    +-- RECOGNITION_BATCH_SIZE (GPU: 256-512, CPU: 32)
    |
    +-- DETECTOR_BATCH_SIZE (GPU: 36-72, CPU: 6)
    |
    +-- COMPILE_* flags (optional, power users)
    |
    v
Model Loading (exists, modify for device)
    |
    +-- Model warm-up (single dummy page)
    |
    v
Batching Strategy (major change)
    |
    +-- Cross-file page collection
    |        |
    |        +-- Page-to-file mapping
    |        |
    |        +-- Result distribution back to files
    |
    +-- Single Surya converter call for all flagged pages
    |
    v
Memory Management
    |
    +-- Post-Surya cleanup
    |
    +-- Model unloading (optional)
```

## MVP Recommendation

Prioritize by impact and complexity:

**Phase 1: Quick Wins (LOW complexity, HIGH impact)**
1. **Explicit MPS device selection** - 10 lines, ensures GPU used
2. **Pass batch_size to Marker** - Set RECOGNITION_BATCH_SIZE, DETECTOR_BATCH_SIZE env vars
3. **Model warm-up** - Run single page after load, hide latency in "loading" phase

**Phase 2: Meaningful Improvement (MEDIUM complexity, HIGH impact)**
4. **VRAM-aware batch sizing** - Detect Apple Silicon variant, set appropriate batch sizes
5. **Post-Surya memory cleanup** - Free GPU memory after Phase 2

**Phase 3: Major Optimization (HIGH complexity, HIGHEST impact)**
6. **Cross-file page batching** - Restructure pipeline for single Surya job across all files

**Defer / Document Only:**
- torch.compile: Document as power-user env var, don't enable by default
- Parallel model loading: Nice optimization but complex threading
- Adaptive batch sizing: Diminishing returns for typical academic PDFs

## Expected Performance Improvements

Based on research, realistic expectations for each optimization:

| Optimization | Expected Speedup | Confidence |
|--------------|------------------|------------|
| Explicit MPS + batch_size env vars | 2-5x | HIGH |
| VRAM-aware larger batches | 1.5-2x additional | MEDIUM |
| Cross-file batching (30 pages vs 3x10) | 2-3x additional | HIGH |
| Model warm-up | No speedup, but consistent timing | HIGH |
| torch.compile | 1.2-1.4x for 100+ pages | LOW (MPS experimental) |

**Cumulative:** With all Phase 1-3 optimizations, expect 5-15x improvement over current sequential per-file processing.

## Implementation Notes

### MPS Device Selection

```python
def get_optimal_device() -> str:
    """Detect best available device."""
    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"

def load_models(device: str | None = None) -> dict[str, Any]:
    device = device or get_optimal_device()
    model_dict = create_model_dict(device=torch.device(device))
    logger.info("Loaded models on device: %s", device)
    return model_dict
```

### Batch Size Environment Configuration

```python
import os

def configure_surya_batch_sizes(device: str) -> None:
    """Set Surya batch sizes based on device."""
    if device == "mps":
        # Apple Silicon unified memory allows larger batches
        os.environ.setdefault("RECOGNITION_BATCH_SIZE", "384")
        os.environ.setdefault("DETECTOR_BATCH_SIZE", "48")
    elif device == "cuda":
        # Conservative defaults for discrete GPU
        os.environ.setdefault("RECOGNITION_BATCH_SIZE", "256")
        os.environ.setdefault("DETECTOR_BATCH_SIZE", "36")
    else:
        # CPU
        os.environ.setdefault("RECOGNITION_BATCH_SIZE", "32")
        os.environ.setdefault("DETECTOR_BATCH_SIZE", "6")
```

### Cross-File Batching Structure

```python
@dataclass
class FlaggedPage:
    file_result: FileResult
    page_number: int
    input_path: Path

def collect_flagged_pages(file_results: list[FileResult]) -> list[FlaggedPage]:
    """Collect all flagged pages across files."""
    return [
        FlaggedPage(fr, p.page_number, input_path)
        for fr in file_results
        for p in fr.flagged_pages
    ]

def batch_process_surya(pages: list[FlaggedPage], model_dict: dict) -> dict[str, str]:
    """Process all flagged pages in single Surya call."""
    # Create temp PDF with all flagged pages
    # Single Surya conversion
    # Map results back to files
    pass
```

## Sources

### Official Documentation (HIGH confidence)
- [Surya GitHub](https://github.com/datalab-to/surya) - RECOGNITION_BATCH_SIZE, DETECTOR_BATCH_SIZE, device configuration
- [Marker GitHub](https://github.com/datalab-to/marker) - Batch processing, multi-GPU, MPS limitations
- [PyTorch MPS Backend](https://docs.pytorch.org/docs/stable/notes/mps.html) - MPS device usage, limitations
- [Apple Developer - Accelerated PyTorch](https://developer.apple.com/metal/pytorch/) - MPS training/inference

### Community/Research (MEDIUM confidence)
- [Marker Issue #164](https://github.com/datalab-to/marker/issues/164) - MPS batch processing limitation (fixed in PR #197)
- [PyTorch MPS Forums](https://discuss.pytorch.org/t/current-state-of-mps/172212) - Current MPS limitations
- WebSearch: "PyTorch MPS Apple Silicon performance optimization 2025"
- WebSearch: "Marker PDF Surya OCR performance optimization batch size MPS 2025"

### Codebase Analysis (HIGH confidence)
- `surya.py` - Current model loading, batch_size configuration gap
- `pipeline.py` - Sequential per-file Surya processing
