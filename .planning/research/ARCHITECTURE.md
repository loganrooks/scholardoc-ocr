# Architecture Patterns: Performance Optimization Integration

**Domain:** OCR Pipeline Performance Optimization
**Researched:** 2026-02-03
**Confidence:** HIGH (based on existing codebase analysis + verified external documentation)

## Current Architecture Overview

```
CLI/MCP Request
       |
       v
+------------------+
|   PipelineConfig |
+------------------+
       |
       v
+------------------+     +-------------------+
|   run_pipeline   |---->| ProcessPoolExecutor|
|   (pipeline.py)  |     | (Tesseract workers)|
+------------------+     +-------------------+
       |                          |
       v                          v
+------------------+     +-------------------+
| Phase 1: Tess    |     | _tesseract_worker |
| (parallel)       |     | (per-file)        |
+------------------+     +-------------------+
       |
       v
+------------------+
| Quality Analysis |
| (per-page scores)|
+------------------+
       |
       v (if flagged pages exist)
+------------------+
| Phase 2: Surya   |
| (sequential/file)|
+------------------+
       |
       v
+------------------+
| surya.load_models| <-- Models loaded once per batch
+------------------+
       |
       v (for each file with flagged pages)
+------------------+
| surya.convert_pdf| <-- Sequential per-file
| (PdfConverter)   |
+------------------+
```

### Current Pain Points

1. **Sequential Per-File Surya Processing**: Lines 378-459 in `pipeline.py` iterate over files sequentially. Each `convert_pdf()` call creates a new `PdfConverter` instance, even though models are shared.

2. **No Cross-File Page Batching**: If 5 files each have 2 flagged pages, we make 5 separate Surya calls instead of one batch of 10 pages. Surya's batch processing optimizations are underutilized.

3. **MCP Model Loading Per-Request**: Each `ocr()` or `ocr_async()` call starts fresh. Models are reloaded even for back-to-back requests.

4. **No MPS Acceleration**: `surya.load_models()` uses auto-detection but doesn't explicitly configure MPS for Apple Silicon.

5. **No Benchmarking Infrastructure**: No way to measure or compare performance across changes.

## Recommended Architecture

### Component Overview

```
CLI/MCP Request
       |
       v
+------------------+
|   PipelineConfig |
+------------------+
       |
       v
+------------------+
|   ModelManager   | <-- NEW: Singleton model cache
|   (model_cache.py)|
+------------------+
       |
       v
+------------------+     +-------------------+
|   run_pipeline   |---->| ProcessPoolExecutor|
|   (pipeline.py)  |     | (Tesseract workers)|
+------------------+     +-------------------+
       |
       v
+------------------+
| Phase 1: Tess    |
+------------------+
       |
       v
+------------------+
| Flagged Page     | <-- NEW: Collect ALL flagged pages
| Aggregation      |      across ALL files
+------------------+
       |
       v
+------------------+
| Phase 2: Surya   | <-- MODIFIED: Single batch call
| (batch_convert)  |     for all flagged pages
+------------------+
       |
       v
+------------------+
| Result Mapping   | <-- NEW: Map batch results
|                  |     back to source files
+------------------+
```

### New Components

#### 1. ModelManager (model_cache.py)

**Purpose:** Singleton that manages Surya model lifecycle with TTL-based eviction.

```python
@dataclass
class ModelCacheConfig:
    device: str | None = None  # None = auto-detect, "mps", "cuda", "cpu"
    ttl_seconds: float = 1800  # 30 minutes default
    preload: bool = False      # Preload on first import

class ModelManager:
    """Singleton manager for Surya model lifecycle."""

    _instance: ModelManager | None = None
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def instance(cls, config: ModelCacheConfig | None = None) -> ModelManager:
        """Get or create the singleton instance."""
        ...

    def get_models(self) -> dict[str, Any]:
        """Get models, loading if needed. Resets TTL on access."""
        ...

    def is_loaded(self) -> bool:
        """Check if models are currently loaded."""
        ...

    def unload(self) -> None:
        """Explicitly unload models to free memory."""
        ...

    def _check_expiry(self) -> None:
        """Background thread to evict stale models."""
        ...
```

**Integration Points:**
- `surya.py`: Modify `load_models()` to delegate to `ModelManager`
- `mcp_server.py`: Access shared models across requests
- `pipeline.py`: Use cached models instead of loading fresh

**Lifecycle:**
1. First request: Models loaded, TTL timer starts
2. Subsequent requests: Models reused, TTL reset
3. TTL expires with no requests: Models evicted, memory freed
4. MCP server shutdown: Explicit cleanup

#### 2. Cross-File Batch Processor (batch.py)

**Purpose:** Aggregate flagged pages across files and process in single Surya batch.

```python
@dataclass
class PageReference:
    """Reference to a specific page in a specific file."""
    file_path: Path
    file_index: int      # Index in batch results
    page_number: int     # 0-indexed page in source PDF
    output_path: Path    # Where final PDF should go

@dataclass
class BatchJob:
    """Collection of pages to process together."""
    pages: list[PageReference]
    temp_dir: Path

    def create_batch_pdf(self) -> Path:
        """Extract all flagged pages into single temp PDF."""
        ...

    def distribute_results(self, batch_text: str) -> dict[Path, dict[int, str]]:
        """Map batch results back to source files."""
        ...

def collect_flagged_pages(
    file_results: list[FileResult],
    input_files: list[Path],
    force_surya: bool = False,
) -> BatchJob | None:
    """Aggregate all flagged pages across files into a BatchJob."""
    ...

def process_batch(
    job: BatchJob,
    model_manager: ModelManager,
    config: SuryaConfig,
) -> dict[Path, dict[int, str]]:
    """Process entire batch and return per-file, per-page results."""
    ...
```

**Data Flow for Cross-File Batching:**

```
File A: Pages 0,1,2 (page 1 flagged)
File B: Pages 0,1,2,3 (pages 2,3 flagged)
File C: Pages 0,1 (page 0 flagged)

         |
         v  collect_flagged_pages()

BatchJob.pages = [
    PageReference(A, 0, 1, output_A),  # A's page 1
    PageReference(B, 1, 2, output_B),  # B's page 2
    PageReference(B, 2, 3, output_B),  # B's page 3
    PageReference(C, 3, 0, output_C),  # C's page 0
]

         |
         v  create_batch_pdf()

temp_batch.pdf: [A_p1, B_p2, B_p3, C_p0]  (4 pages total)

         |
         v  surya.convert_pdf(temp_batch.pdf)

Single Surya call processes all 4 pages

         |
         v  distribute_results()

{
    output_A: {1: "text for A page 1"},
    output_B: {2: "text for B page 2", 3: "text for B page 3"},
    output_C: {0: "text for C page 0"},
}
```

#### 3. Device Configuration (device.py)

**Purpose:** Explicit device selection with MPS support.

```python
from enum import StrEnum

class Device(StrEnum):
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"

def detect_device() -> str:
    """Detect best available device."""
    import torch

    if torch.backends.mps.is_available():
        return "mps"
    elif torch.cuda.is_available():
        return "cuda"
    return "cpu"

def resolve_device(requested: str | Device | None) -> str:
    """Resolve requested device to actual torch device string."""
    if requested is None or requested == Device.AUTO:
        return detect_device()
    return str(requested)

def validate_mps() -> bool:
    """Check if MPS is functional (not just available)."""
    # Some MPS operations have bugs; test basic functionality
    ...
```

**Integration:**
- `ModelCacheConfig.device` uses this
- `SuryaConfig` extended with `device` parameter
- Environment variable `SCHOLARDOC_DEVICE` for override

#### 4. Benchmarking Infrastructure (benchmarks/)

**Purpose:** Performance regression testing and comparison.

```
benchmarks/
    conftest.py          # pytest-benchmark fixtures
    test_surya_batch.py  # Batch size benchmarks
    test_pipeline.py     # End-to-end benchmarks
    data/
        sample_10page.pdf
        sample_50page.pdf
        sample_academic.pdf  # Dense text, complex layout
```

**Benchmark Categories:**

1. **Model Loading**: Time to load Surya models (cold vs cached)
2. **Batch Processing**: Pages/second at different batch sizes
3. **Device Comparison**: CPU vs MPS performance
4. **End-to-End Pipeline**: Full Tesseract+Surya workflow

### Modified Components

#### pipeline.py Changes

**Current (lines 348-465):**
```python
# Sequential per-file Surya
for file_result in flagged_results:
    # ... extract pages, convert, map back
```

**Proposed:**
```python
# Batch all flagged pages
from .batch import collect_flagged_pages, process_batch
from .model_cache import ModelManager

if flagged_results:
    # Collect all flagged pages across all files
    batch_job = collect_flagged_pages(
        flagged_results, input_files, config.force_surya
    )

    if batch_job and batch_job.pages:
        # Load models (cached if available)
        model_manager = ModelManager.instance()

        # Single batch call for all pages
        results_map = process_batch(
            batch_job, model_manager, surya_cfg
        )

        # Apply results back to file outputs
        for file_result in flagged_results:
            apply_surya_results(file_result, results_map)
```

#### surya.py Changes

**Current:**
```python
def load_models(device: str | None = None) -> dict[str, Any]:
    """Load Surya/Marker models once for reuse."""
    ...
```

**Proposed:**
```python
def load_models(
    device: str | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Load Surya/Marker models, optionally from cache."""
    if use_cache:
        from .model_cache import ModelManager, ModelCacheConfig
        config = ModelCacheConfig(device=device)
        return ModelManager.instance(config).get_models()

    # Original implementation for explicit non-cached use
    ...
```

#### mcp_server.py Changes

**Current:** Each request calls `run_pipeline()` which loads models fresh.

**Proposed:**
```python
# At module level or in main()
from .model_cache import ModelManager, ModelCacheConfig

def _ensure_models_ready():
    """Pre-warm models if configured."""
    config = ModelCacheConfig(
        device=os.environ.get("SCHOLARDOC_DEVICE"),
        ttl_seconds=float(os.environ.get("SCHOLARDOC_MODEL_TTL", 1800)),
    )
    ModelManager.instance(config)

# In ocr() and ocr_async():
# Models automatically shared via ModelManager singleton
```

## Component Boundaries

| Component | Responsibility | Depends On |
|-----------|---------------|------------|
| `model_cache.py` | Model lifecycle, TTL eviction | `surya.py`, `device.py` |
| `device.py` | Device detection, MPS validation | PyTorch |
| `batch.py` | Page aggregation, result mapping | `processor.py`, `model_cache.py` |
| `pipeline.py` | Orchestration (uses batch module) | All above |
| `mcp_server.py` | Request handling (uses cached models) | `pipeline.py`, `model_cache.py` |

## Data Flow Changes

### Before (Current)

```
File 1 flagged pages -> Surya call 1 -> Result 1
File 2 flagged pages -> Surya call 2 -> Result 2
File 3 flagged pages -> Surya call 3 -> Result 3
```

### After (Cross-File Batching)

```
File 1 flagged pages -+
File 2 flagged pages -+-> Aggregate -> Single Surya call -> Distribute results
File 3 flagged pages -+
```

### Memory Timeline

**Current:**
```
Request 1: [Load models ~~~~~ Process ~~~~~ Unload]
Request 2: [Load models ~~~~~ Process ~~~~~ Unload]
                ^^ Redundant 30-60s model load
```

**With Caching:**
```
Request 1: [Load models ~~~~~ Process ~~~~~]
Request 2:                    [Process ~~~~~]
                              ^^ Instant start
           [...TTL expires...] [Unload]
```

## Suggested Build Order

Based on dependencies and risk:

### Phase 1: Device Configuration (Foundation)
1. Create `device.py` with device detection
2. Add `SCHOLARDOC_DEVICE` environment variable support
3. Verify MPS works for Surya operations
4. Unit tests for device detection

**Rationale:** Low risk, enables MPS testing. No changes to core pipeline.

### Phase 2: Model Caching (High Value)
1. Create `model_cache.py` with ModelManager singleton
2. Thread-safe model access with TTL eviction
3. Modify `surya.py` to use cache by default
4. Update `mcp_server.py` to share models across requests
5. Add model preload option

**Rationale:** Highest impact on MCP server performance. Independent of batching.

### Phase 3: Cross-File Batching (Complex)
1. Create `batch.py` with BatchJob infrastructure
2. Add page extraction/aggregation logic
3. Implement result distribution back to files
4. Modify `pipeline.py` to use batch processing
5. Integration tests with multi-file batches

**Rationale:** Most complex change, benefits from stable model caching.

### Phase 4: Benchmarking (Validation)
1. Add `pytest-benchmark` dependency
2. Create benchmark fixtures and sample data
3. Baseline benchmarks for current performance
4. Comparative benchmarks for optimizations
5. CI integration for regression detection

**Rationale:** Validates previous phases, catches regressions.

## Scalability Considerations

| Concern | At 10 pages | At 100 pages | At 1000 pages |
|---------|-------------|--------------|---------------|
| Batch PDF size | ~5MB | ~50MB | ~500MB |
| Surya memory | ~3GB | ~5GB | ~8GB+ |
| Temp disk | Negligible | ~100MB | ~1GB |
| Processing time | ~30s | ~2min | ~15min |

**Recommendations:**
- For 1000+ pages, implement chunked batching (process 100 pages at a time)
- Monitor memory pressure on MPS (Apple Silicon sensitive to memory)
- Consider `PYTORCH_MPS_HIGH_WATERMARK_RATIO` for memory-constrained systems

## Anti-Patterns to Avoid

### 1. Loading Models in Worker Processes
**Wrong:** Loading Surya models inside `_tesseract_worker`
**Why:** Worker processes can't share GPU memory; models would load N times
**Instead:** Keep models in main process, batch Surya in main thread

### 2. Global Singleton Without Lifecycle Management
**Wrong:** `_models = None; def get_models(): global _models; ...`
**Why:** No TTL, no cleanup, memory leak on long-running server
**Instead:** ModelManager class with explicit lifecycle

### 3. Mixing Async and Synchronous Model Access
**Wrong:** Calling `ModelManager.get_models()` from both sync and async code
**Why:** Thread safety issues, potential deadlocks
**Instead:** Always access from sync context; use `asyncio.to_thread()` for async wrappers

### 4. Assuming MPS Parity with CUDA
**Wrong:** Expecting identical batch sizes and performance on MPS
**Why:** MPS has different memory characteristics and some ops fall back to CPU
**Instead:** Profile on target device, adjust batch sizes accordingly

## Configuration Schema

```python
# Extended PipelineConfig
@dataclass
class PipelineConfig:
    # ... existing fields ...

    # New performance fields
    device: str | None = None           # None = auto-detect
    use_model_cache: bool = True        # Enable model caching
    model_ttl_seconds: float = 1800     # Cache TTL (30 min)
    batch_cross_files: bool = True      # Enable cross-file batching
    surya_batch_size: int = 50          # Pages per Surya batch
```

## Sources

- [PyTorch MPS Backend Documentation](https://docs.pytorch.org/docs/stable/notes/mps.html) - MPS requirements, capabilities, limitations
- [Apple Developer: Accelerated PyTorch Training on Mac](https://developer.apple.com/metal/pytorch/) - Unified memory benefits, setup
- [Marker GitHub Repository](https://github.com/VikParuchuri/marker) - PdfConverter usage, batch processing
- [Surya GitHub Repository](https://github.com/datalab-to/surya) - Device configuration, batch size settings
- [pytest-benchmark Documentation](https://pytest-benchmark.readthedocs.io/) - Benchmarking fixture usage
- [Streamlit Caching Guide](https://docs.streamlit.io/develop/concepts/architecture/caching) - Singleton pattern for ML models
