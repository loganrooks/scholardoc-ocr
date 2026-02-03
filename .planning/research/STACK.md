# Technology Stack: Surya/PyTorch Performance Optimization

**Project:** scholardoc-ocr Performance Milestone
**Researched:** 2026-02-03
**Scope:** Stack additions for MPS/Metal acceleration, batch optimization, memory profiling, benchmarking

## Executive Summary

Performance optimization on Apple Silicon requires minimal new production dependencies but significant dev/profiling tooling. PyTorch MPS backend works out-of-the-box when detected. The real work is configuration tuning (batch sizes, device selection) and measurement infrastructure.

**Key finding:** Surya/Marker already auto-detects MPS. The gap is not "enable MPS" but "optimize for MPS" -- batch sizes, memory pressure, and profiling to find optimal settings.

## Production Dependencies

### No New Production Dependencies Required

| Current Package | Version | MPS Status | Action |
|-----------------|---------|------------|--------|
| `marker-pdf` | >=1.0.0 (current: 1.10.2) | Uses PyTorch MPS auto-detect | No change |
| `torch` (via marker-pdf) | Transitive | MPS available on macOS 12.3+ | No change |

**Rationale:** PyTorch (bundled with marker-pdf) already includes MPS backend. From the [PyTorch MPS documentation](https://docs.pytorch.org/docs/stable/notes/mps.html):

```python
import torch
if torch.backends.mps.is_available():
    device = torch.device("mps")
```

Current `surya.py` already accepts a `device` parameter in `load_models()`. The infrastructure exists; optimization is configuration.

### Optional: safetensors for Faster Model Loading

| Package | Version | Purpose | Priority |
|---------|---------|---------|----------|
| `safetensors` | >=0.7.0 | Memory-mapped model loading | OPTIONAL |

**Why consider:** [safetensors](https://github.com/huggingface/safetensors) provides memory-mapped tensor loading, avoiding the 2x memory spike of pickle-based loading. For Surya models (~3.5GB), this could reduce cold-start memory pressure.

**Why optional:** Marker-pdf may already use safetensors internally. Verify before adding.

```bash
# Only add if marker-pdf doesn't already use it
pip install safetensors>=0.7.0
```

## Development/Profiling Dependencies

### Benchmarking Tools

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| `pytest-benchmark` | >=5.2.3 | Integrated benchmark suite | YES |
| `hyperfine` | System tool | CLI-level end-to-end timing | YES |

**pytest-benchmark** ([docs](https://pytest-benchmark.readthedocs.io/)):
- Integrates with existing pytest infrastructure
- Statistical analysis across runs (min, max, mean, stddev)
- Comparison between runs with `--benchmark-compare`
- Export to JSON for tracking

```toml
# pyproject.toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.4.0",
    "pytest-benchmark>=5.2.3",  # NEW
]
```

**hyperfine** ([GitHub](https://github.com/sharkdp/hyperfine)):
- End-to-end CLI benchmarking
- Warmup runs, statistical outlier detection
- Compare before/after in shell

```bash
# Install via homebrew on macOS
brew install hyperfine

# Usage
hyperfine --warmup 2 'ocr test.pdf' 'ocr --mps test.pdf'
```

### Memory Profiling

| Package | Version | Purpose | Required |
|---------|---------|---------|----------|
| `memray` | >=1.19.1 | Heap profiling, flame graphs | YES |
| `scalene` | >=2.1.3 | Line-level CPU/memory profiling | OPTIONAL |

**memray** ([docs](https://bloomberg.github.io/memray/)):
- Tracks Python and native (C/C++) memory allocations
- Critical for PyTorch since model memory is in native extensions
- Flame graph visualization
- pytest integration via `pytest-memray`

```toml
[project.optional-dependencies]
dev = [
    # ... existing ...
    "memray>=1.19.1",  # NEW
]
perf = [
    "pytest-benchmark>=5.2.3",
    "memray>=1.19.1",
]
```

**memray usage:**
```bash
# Profile entire run
python -m memray run -o output.bin -m scholardoc_ocr.cli test.pdf
python -m memray flamegraph output.bin

# With native tracking (includes PyTorch C++)
python -m memray run --native -o output.bin -m scholardoc_ocr.cli test.pdf
```

**scalene** ([GitHub](https://github.com/plasma-umass/scalene)):
- Line-level CPU profiling
- Separates Python time from native code time
- GPU profiling (NVIDIA only, not MPS)
- AI-powered optimization suggestions

**Note on scalene:** GPU profiling is NVIDIA-only. For MPS profiling, use `torch.mps.profiler` instead.

### PyTorch Profiling (Built-in)

No additional package needed. PyTorch includes MPS-specific profiling:

```python
import torch

# MPS-specific profiler (generates OS Signposts for Xcode Instruments)
with torch.mps.profiler.profile(mode="interval", wait_until_completed=False):
    # Model operations here
    pass

# Standard PyTorch profiler also works
with torch.profiler.profile() as prof:
    # Model operations
    pass
print(prof.key_averages().table())
```

## Environment Variables for Surya/MPS Optimization

From [Surya documentation](https://github.com/datalab-to/surya), these control batch sizes and memory:

| Variable | Default (GPU) | Default (CPU) | Memory per Item | Notes |
|----------|---------------|---------------|-----------------|-------|
| `RECOGNITION_BATCH_SIZE` | 512 | 32 | ~40MB | Text recognition |
| `DETECTOR_BATCH_SIZE` | 36 | 6 | ~440MB | Line detection |
| `LAYOUT_BATCH_SIZE` | 32 | 4 | ~220MB | Layout analysis |
| `TABLE_REC_BATCH_SIZE` | 64 | 8 | ~150MB | Table recognition |
| `TORCH_DEVICE` | auto-detect | - | - | Override device selection |

**Apple Silicon tuning strategy:**
1. Start with GPU defaults
2. Monitor unified memory pressure via `memray` or Activity Monitor
3. Reduce batch sizes if memory pressure causes swap
4. MPS has no separate VRAM -- unified memory means CPU/GPU share the pool

**Example configuration script:**
```bash
export TORCH_DEVICE=mps
export RECOGNITION_BATCH_SIZE=256  # Halved from default
export DETECTOR_BATCH_SIZE=18      # Halved from default
```

## MPS Configuration Specifics

### Enabling MPS in scholardoc-ocr

Current `surya.py` already supports explicit device:
```python
def load_models(device: str | None = None) -> dict[str, Any]:
    if device is not None:
        import torch
        model_dict = create_model_dict(device=torch.device(device))
    else:
        model_dict = create_model_dict()  # Auto-detect (will use MPS if available)
```

**Recommended changes:**
1. Add `--mps` / `--cpu` CLI flags to force device selection
2. Add device info to logging output
3. Add MPS availability check to validation module

### MPS Fallback Handling

Some operations may not be implemented in MPS. Handle gracefully:

```bash
# Enable CPU fallback for unsupported ops
export PYTORCH_ENABLE_MPS_FALLBACK=1
```

```python
# Programmatic check
import torch
if torch.backends.mps.is_available():
    if not torch.backends.mps.is_built():
        logger.warning("MPS not built into this PyTorch installation")
    device = "mps"
else:
    device = "cpu"
```

### Known MPS Limitations (PyTorch 2.10)

| Limitation | Impact | Mitigation |
|------------|--------|------------|
| No float64 support | Some ops may fail | Use float32 (Surya already does) |
| No distributed training | N/A | Single-GPU use case anyway |
| `torch.compile` limited | Some optimizations skip | Run in eager mode (default) |
| macOS 26.0 (Tahoe) initial release bug | MPS shows "built" but "not available" | Upgrade to macOS 26.1+ |

**Sources:** [PyTorch GitHub issue #167679](https://github.com/pytorch/pytorch/issues/167679) confirms macOS 26.1 fixes the availability bug.

### Memory Synchronization

MPS operations are asynchronous. For accurate timing:

```python
import torch

def timed_inference():
    start = time.perf_counter()
    result = model(input)
    torch.mps.synchronize()  # Wait for GPU to finish
    elapsed = time.perf_counter() - start
    return result, elapsed
```

## Model Caching Strategy

### Current State

Models are loaded per-pipeline run. For batch processing, this is acceptable. For MCP server (long-running), models could be cached in memory.

### Recommended Approach

| Strategy | Implementation | Tradeoff |
|----------|---------------|----------|
| Lazy load on first call | Current behavior | Cold start per session |
| Pre-load on server startup | Load models in MCP `__init__` | ~3.5GB constant memory |
| LRU cache with timeout | Cache models, unload after idle | Complexity vs benefit |

**For MCP server:** Pre-load on startup is likely correct. The MCP server is expected to handle multiple requests; loading models once is worth the memory cost.

```python
# mcp_server.py
class SuryaModelCache:
    _models: dict | None = None

    @classmethod
    def get_models(cls, device: str | None = None) -> dict:
        if cls._models is None:
            cls._models = surya.load_models(device=device)
        return cls._models

    @classmethod
    def unload(cls):
        cls._models = None
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
```

## What NOT to Add

| Package | Why Tempting | Why Wrong |
|---------|-------------|-----------|
| `mlx` / `mlx-lm` | Apple's optimized framework, 2-3x faster than PyTorch MPS for some workloads | Requires rewriting Surya integration. Marker/Surya use PyTorch. Not worth the rewrite. |
| `accelerate` | Hugging Face's training acceleration | Optimized for training, not inference. Surya handles its own device placement. |
| `onnxruntime` with CoreML | Could compile models to CoreML | Major engineering effort. Surya models aren't ONNX-exported. |
| `triton` | Kernel optimization | NVIDIA-focused. No MPS backend. |
| `tensorrt` | Inference optimization | NVIDIA-only. |

**Philosophy:** Work with the existing stack (PyTorch + Marker + Surya). Don't replace proven components for marginal gains.

## Changes to pyproject.toml

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "ruff>=0.4.0",
    "pytest-benchmark>=5.2.3",
    "memray>=1.19.1",
]
mcp = ["mcp[cli]"]
perf = [
    # All profiling tools for performance work
    "pytest-benchmark>=5.2.3",
    "memray>=1.19.1",
]
```

**System tools (not pip-installable):**
```bash
brew install hyperfine  # CLI benchmarking
```

## New Modules to Create

| Module | Purpose |
|--------|---------|
| `src/scholardoc_ocr/perf.py` | Device detection, MPS helpers, timing utilities |
| `benchmarks/` directory | pytest-benchmark test files |
| `scripts/benchmark.sh` | hyperfine end-to-end benchmarks |

## Integration Points

| Existing Module | Performance Integration |
|-----------------|------------------------|
| `surya.py` | Add device parameter to `SuryaConfig`, log device selection |
| `pipeline.py` | Pass device config to Surya, add timing instrumentation |
| `cli.py` | Add `--mps`, `--cpu`, `--benchmark` flags |
| `mcp_server.py` | Model cache singleton, device reporting in health check |
| `validation.py` | Add MPS availability check |

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| PyTorch MPS availability | HIGH | Verified [official PyTorch docs](https://docs.pytorch.org/docs/stable/notes/mps.html) |
| Surya batch size env vars | HIGH | Verified [Surya GitHub README](https://github.com/datalab-to/surya) |
| memray macOS support | HIGH | Verified [PyPI page](https://pypi.org/project/memray/) shows macOS 15.0+ ARM64 |
| pytest-benchmark features | HIGH | Verified [official docs](https://pytest-benchmark.readthedocs.io/) |
| MPS `torch.compile` limitations | MEDIUM | WebSearch sources, not official PyTorch docs |
| safetensors benefit for Marker | LOW | Need to verify if Marker already uses it |

## Sources

- [PyTorch MPS Backend Documentation](https://docs.pytorch.org/docs/stable/notes/mps.html) - Official PyTorch docs
- [Apple Developer PyTorch Guide](https://developer.apple.com/metal/pytorch/) - Apple's official guidance
- [Surya OCR GitHub](https://github.com/datalab-to/surya) - Environment variables and configuration
- [marker-pdf PyPI](https://pypi.org/project/marker-pdf/) - Version 1.10.2, Python 3.10+
- [memray Documentation](https://bloomberg.github.io/memray/) - Memory profiling
- [pytest-benchmark Documentation](https://pytest-benchmark.readthedocs.io/) - Version 5.2.3
- [scalene GitHub](https://github.com/plasma-umass/scalene) - Line-level profiling
- [hyperfine GitHub](https://github.com/sharkdp/hyperfine) - CLI benchmarking
- [safetensors GitHub](https://github.com/huggingface/safetensors) - Fast tensor loading
- [PyTorch GitHub Issue #167679](https://github.com/pytorch/pytorch/issues/167679) - macOS 26.0 MPS bug (fixed in 26.1)
