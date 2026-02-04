# Phase 12: Device Configuration - Research

**Researched:** 2026-02-04
**Domain:** PyTorch device management, Apple Silicon MPS, GPU acceleration
**Confidence:** MEDIUM

## Summary

This phase implements device configuration for GPU acceleration in the scholardoc-ocr pipeline, specifically targeting Apple Silicon MPS (Metal Performance Shaders) with CUDA support and CPU fallback. The research reveals that while PyTorch provides robust device detection and management APIs, the Marker/Surya OCR library has a documented MPS bug in the detection model that requires a workaround.

The key architectural challenge is that Marker's `create_model_dict()` function uses a **unified device setting** for all models. The desired detection/recognition split (detection on CPU, recognition on GPU) is not natively supported by Marker and will require custom implementation at a higher level in the pipeline.

**Primary recommendation:** Implement a device manager module that handles auto-detection, validation, and fallback, with a two-pass strategy for MPS: first run with all models on MPS, and on failure, fall back to full CPU mode. The detection/recognition split workaround should be implemented by loading two separate model dictionaries if granular control is needed, though this doubles memory usage.

## Standard Stack

The implementation relies entirely on existing dependencies already in the project.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| torch | (via marker-pdf) | Device management, tensor operations | PyTorch's `torch.device`, `torch.backends.mps`, `torch.cuda` are the standard APIs |
| marker-pdf | >=1.0.0 | OCR models via `create_model_dict()` | Already in use; provides unified model loading |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none needed) | - | - | All device management uses torch APIs |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Manual device checks | pytorch-lightning Trainer | Overkill; we don't need training infrastructure |
| Custom device manager | accelerate library | Adds dependency; designed for distributed training |

**Installation:** No new packages required - all device management uses PyTorch which is already a dependency of marker-pdf.

## Architecture Patterns

### Recommended Project Structure

Add a new module for device management:

```
src/scholardoc_ocr/
├── device.py          # NEW: Device detection, validation, fallback
├── surya.py           # MODIFY: Accept device config from device.py
├── pipeline.py        # MODIFY: Initialize device manager at startup
└── types.py           # MODIFY: Add device info to result metadata
```

### Pattern 1: Device Auto-Detection with Priority Order

**What:** Centralized device detection following CUDA > MPS > CPU priority
**When to use:** At pipeline startup before loading any models
**Example:**
```python
# Source: PyTorch docs + verified patterns
import torch

def get_best_device() -> torch.device:
    """Detect best available device with priority: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")
```

### Pattern 2: MPS Availability Check with Build Verification

**What:** Comprehensive MPS check that distinguishes "not built" from "not available"
**When to use:** When validating MPS on Apple Silicon
**Example:**
```python
# Source: PyTorch MPS backend docs
# https://github.com/pytorch/pytorch/blob/main/docs/source/notes/mps.rst
if not torch.backends.mps.is_available():
    if not torch.backends.mps.is_built():
        print("MPS not available: PyTorch not built with MPS enabled.")
    else:
        print("MPS not available: macOS version < 12.3 or no MPS device.")
else:
    mps_device = torch.device("mps")
```

### Pattern 3: OOM Error Handling with Retry

**What:** Handle out-of-memory errors by moving recovery code outside except clause
**When to use:** When GPU memory is exhausted during inference
**Example:**
```python
# Source: PyTorch FAQ - Handle Out of Memory Exception
# https://github.com/pytorch/pytorch/blob/main/docs/source/notes/faq.rst
oom = False
try:
    run_model(batch_size)
except RuntimeError:  # Out of memory
    oom = True

if oom:
    # Recovery MUST be outside except to allow memory cleanup
    torch.cuda.empty_cache()  # or torch.mps.empty_cache() on MPS
    for _ in range(batch_size):
        run_model(1)
```

### Pattern 4: Device-Agnostic Model Loading

**What:** Move models to desired device after loading
**When to use:** When you need to override Marker's default device
**Example:**
```python
# Source: PyTorch Modules docs
# https://github.com/pytorch/pytorch/blob/main/docs/source/notes/modules.rst
device = get_best_device()
model_dict = create_model_dict(device=str(device))
# Models are already on correct device; no need to call .to()
```

### Anti-Patterns to Avoid

- **Checking CUDA without try/except:** CUDA operations can fail at runtime even when `is_available()` returns True
- **Handling OOM inside except clause:** Python exception object retains stack frame reference, preventing memory cleanup
- **Using `model.to(device)` repeatedly:** Expensive operation; set device once at load time
- **Ignoring MPS synchronization:** MPS operations are asynchronous; call `torch.mps.synchronize()` before timing

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Device detection | Custom platform checks | `torch.cuda.is_available()`, `torch.backends.mps.is_available()` | Handles edge cases, version checks |
| Memory cleanup | Manual del/gc | `torch.cuda.empty_cache()` / `torch.mps.empty_cache()` | Proper allocator interaction |
| GPU synchronization | sleep/polling | `torch.cuda.synchronize()` / `torch.mps.synchronize()` | Proper kernel completion |
| Hardware detection | Platform sniffing | Existing `timing.get_hardware_profile()` | Already implemented in codebase |

**Key insight:** PyTorch's device management is mature and handles hardware variations. The complexity is in the Marker integration, not in device detection itself.

## Common Pitfalls

### Pitfall 1: MPS Detection Bug in Surya

**What goes wrong:** The detection model fails silently or produces incorrect results on MPS
**Why it happens:** Known Apple-side bug in MPS with certain tensor operations in Surya's detection model
**How to avoid:** Use the documented workaround - run all models on CPU via `TORCH_DEVICE=cpu` or accept full MPS with potential issues
**Warning signs:** Silent failures in text detection, incomplete bounding boxes, different results on CPU vs MPS

### Pitfall 2: OOM Recovery Memory Leak

**What goes wrong:** Memory isn't freed when handling out-of-memory errors
**Why it happens:** Python exception object holds reference to stack frame; objects in local variables aren't freed
**How to avoid:** Set a flag in except clause, handle recovery OUTSIDE the except block
**Warning signs:** Memory usage stays high after OOM, subsequent operations also fail with OOM

### Pitfall 3: MPS Multiprocessing Incompatibility

**What goes wrong:** "Cannot use MPS with torch multiprocessing share_memory" error
**Why it happens:** PyTorch's `share_memory()` doesn't support MPS device
**How to avoid:** Don't use ProcessPoolExecutor with MPS tensors; process in main thread or use `marker_single` pattern
**Warning signs:** Error on first multiprocessing operation with MPS tensors

### Pitfall 4: Async MPS Operations Timing

**What goes wrong:** Timing measurements show incorrect (too fast) results
**Why it happens:** MPS operations are asynchronous; `time.time()` returns before GPU work completes
**How to avoid:** Call `torch.mps.synchronize()` before timing measurements (already in `timing.mps_sync()`)
**Warning signs:** Inference appears instant, timings vary wildly

### Pitfall 5: MPS Not Available on macOS 26 Tahoe

**What goes wrong:** MPS shows as "built" but not "available" on newest macOS
**Why it happens:** PyTorch 2.9.1/2.10.0 bug with macOS 26 (Tahoe) - tracked in [pytorch#167679](https://github.com/pytorch/pytorch/issues/167679)
**How to avoid:** Graceful fallback to CPU when MPS is built but not available
**Warning signs:** `torch.backends.mps.is_built()` True but `torch.backends.mps.is_available()` False

## Code Examples

Verified patterns from official sources:

### Device Manager Class

```python
# Recommended implementation pattern
import logging
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import torch

logger = logging.getLogger(__name__)


class DeviceType(StrEnum):
    CUDA = "cuda"
    MPS = "mps"
    CPU = "cpu"


@dataclass
class DeviceInfo:
    """Information about the selected compute device."""
    device_type: DeviceType
    device_name: str  # e.g., "NVIDIA A100", "Apple M2", "cpu"
    validated: bool = False
    fallback_from: DeviceType | None = None


def detect_device() -> DeviceInfo:
    """Detect best available device with validation.

    Priority: CUDA > MPS > CPU
    """
    import torch  # Lazy import

    # Try CUDA first
    if torch.cuda.is_available():
        try:
            # Validation: allocate small tensor
            _ = torch.zeros(1, device="cuda")
            name = torch.cuda.get_device_name(0)
            logger.info("Using device: cuda (%s)", name)
            return DeviceInfo(
                device_type=DeviceType.CUDA,
                device_name=name,
                validated=True,
            )
        except RuntimeError as e:
            logger.warning("CUDA available but validation failed: %s", e)

    # Try MPS second (Apple Silicon)
    if torch.backends.mps.is_available():
        try:
            # Validation: allocate small tensor
            _ = torch.zeros(1, device="mps")
            logger.info("Using device: mps")
            return DeviceInfo(
                device_type=DeviceType.MPS,
                device_name="Apple Silicon",
                validated=True,
            )
        except RuntimeError as e:
            logger.warning("MPS available but validation failed: %s", e)

    # Fallback to CPU
    logger.info("Using device: cpu")
    return DeviceInfo(
        device_type=DeviceType.CPU,
        device_name="cpu",
        validated=True,
    )
```

### Fallback-Aware Model Loading

```python
# Source: Marker docs + PyTorch patterns
def load_models_with_fallback(
    device_info: DeviceInfo,
    strict_gpu: bool = False,
) -> dict:
    """Load Marker models with device fallback on failure.

    Args:
        device_info: Detected device information
        strict_gpu: If True, fail instead of falling back to CPU

    Returns:
        Model dictionary from create_model_dict()

    Raises:
        RuntimeError: If strict_gpu=True and GPU loading fails
    """
    from marker.models import create_model_dict
    import torch

    device_str = str(device_info.device_type)

    try:
        logger.info("Loading models on %s...", device_str)
        model_dict = create_model_dict(device=device_str)
        # Sync to ensure models are fully loaded
        if device_info.device_type == DeviceType.MPS:
            torch.mps.synchronize()
        elif device_info.device_type == DeviceType.CUDA:
            torch.cuda.synchronize()
        return model_dict

    except RuntimeError as e:
        if strict_gpu:
            raise RuntimeError(
                f"GPU model loading failed and --strict-gpu enabled: {e}"
            ) from e

        logger.warning(
            "Failed to load models on %s, falling back to CPU: %s",
            device_str, e
        )
        return create_model_dict(device="cpu")
```

### OOM-Safe Inference Wrapper

```python
# Source: PyTorch FAQ OOM handling pattern
def inference_with_oom_fallback(
    converter,
    input_path: str,
    batch_size: int = 50,
    min_batch_size: int = 1,
) -> str:
    """Run inference with OOM recovery.

    On OOM: halve batch size until min_batch_size, then fail.
    """
    import torch

    current_batch = batch_size

    while current_batch >= min_batch_size:
        oom = False
        try:
            result = converter(input_path)
            return result.markdown
        except RuntimeError as e:
            if "out of memory" in str(e).lower():
                oom = True
            else:
                raise

        if oom:
            # Memory cleanup OUTSIDE except block
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()

            current_batch = max(min_batch_size, current_batch // 2)
            logger.warning(
                "OOM detected, reducing batch size to %d", current_batch
            )
            # Recreate converter with smaller batch size
            converter.config.batch_size = current_batch

    raise RuntimeError(f"OOM even at minimum batch size {min_batch_size}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual CUDA device selection | Auto-detect CUDA > MPS > CPU | PyTorch 1.12 (MPS) | Unified device handling |
| CPU-only fallback | MPS on Apple Silicon | PyTorch 1.12 / 2022 | 2-5x speedup on M-series |
| Fixed batch sizes | Dynamic batch with OOM retry | Best practice 2024+ | Better resource utilization |
| Global TORCH_DEVICE env var | Programmatic device= parameter | Marker 1.0+ | Cleaner API |

**Deprecated/outdated:**
- `CUDA_VISIBLE_DEVICES=""` for CPU forcing: Use `device="cpu"` parameter instead
- `torch.cuda.empty_cache()` called inside except: Memory leak risk; call outside

## Open Questions

Things that couldn't be fully resolved:

1. **Detection/Recognition Split Granularity**
   - What we know: Marker's `create_model_dict()` applies one device to all models
   - What's unclear: Whether individual models can be moved to different devices after loading without breaking Marker internals
   - Recommendation: Test empirically; may need to load two model dicts (one CPU, one MPS) and selectively use them, or accept the limitation and run all models on same device

2. **MPS Bug Timeline**
   - What we know: Detection model has documented Apple-side bug with MPS
   - What's unclear: When/if Apple will fix the underlying Metal bug, or if Marker will work around it
   - Recommendation: Design for easy re-enablement; use feature flag or config to toggle the workaround

3. **Thread Safety of Device Manager**
   - What we know: PyTorch device objects are lightweight and thread-safe
   - What's unclear: Whether Marker's model loading has thread-safety guarantees
   - Recommendation: Load models once in main thread, share read-only across workers (current pipeline pattern)

## Sources

### Primary (HIGH confidence)

- **Context7: /pytorch/pytorch** - MPS backend docs, device management, OOM handling
  - Topics: `torch.backends.mps.is_available()`, `torch.device`, OOM patterns
- **Context7: /datalab-to/marker** - Model loading, device configuration
  - Topics: `create_model_dict()`, device parameter, model dictionary structure

### Secondary (MEDIUM confidence)

- **PyTorch MPS Documentation** (https://docs.pytorch.org/docs/stable/notes/mps.html) - MPS setup and fallback environment variable
- **Marker GitHub Issue #255** (https://github.com/datalab-to/marker/issues/255) - MPS multiprocessing incompatibility workaround
- **DeepWiki Marker Model Management** (https://deepwiki.com/datalab-to/marker/5.7-model-management) - Unified device selection architecture

### Tertiary (LOW confidence)

- **Web Search: MPS detection bug** - Referenced Apple-side bug in Surya; no official PyTorch/Apple acknowledgment found
- **Web Search: PyTorch 167679** - MPS not available on macOS 26; GitHub issue exists but resolution unclear

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Uses only PyTorch APIs already in project
- Architecture: MEDIUM - Detection/recognition split may require empirical testing
- Pitfalls: HIGH - Well-documented in official sources

**Research date:** 2026-02-04
**Valid until:** 2026-03-04 (30 days - stable domain, but MPS bugs may evolve)

---

## Implementation Notes for Planner

### Critical Constraints from CONTEXT.md

1. **Device Selection:** Auto-detect, no user configuration required. Priority: CUDA > MPS > CPU
2. **Fallback Strategy:** Log at WARNING, include in result metadata, OOM triggers batch reduction then CPU fallback
3. **Detection/Recognition Split:** Detection on CPU, recognition on GPU - this is a workaround for MPS bugs
4. **--strict-gpu flag:** CLI option to disable CPU fallback

### Architecture Recommendations

1. Create `device.py` module with `DeviceManager` class
2. Device detection should happen once at startup (lazy on first use is acceptable)
3. Validation can be shallow (flag check) or deep (tensor allocation) - deep is safer
4. Result metadata should include: device used, whether fallback occurred, per-page device info
5. The detection/recognition split may not be implementable with current Marker API - consider loading two model dicts or accepting full-CPU fallback as the workaround
