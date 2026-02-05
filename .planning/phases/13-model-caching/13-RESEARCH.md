# Phase 13: Model Caching - Research

**Researched:** 2026-02-04
**Domain:** ML model lifecycle management, TTL-based caching, GPU memory cleanup
**Confidence:** MEDIUM

## Summary

This phase implements model caching for the MCP server to eliminate repeated 30-60 second model loading delays between requests. The current architecture loads Surya/Marker models fresh for each request in `pipeline.py` via `surya.load_models()`. The MCP server in `mcp_server.py` processes each request independently, meaning every OCR job pays the full model loading cost.

The solution involves creating a singleton model cache with time-to-live (TTL) expiration, proper GPU memory cleanup between documents, and optional warm-loading at server startup. The cachetools library provides the TTLCache primitive needed, while PyTorch's `empty_cache()` handles GPU memory reclamation.

**Primary recommendation:** Create a `model_cache.py` module with a `ModelCache` class that wraps `surya.load_models()`, stores the result with a configurable TTL, and provides memory cleanup hooks between documents. Use FastMCP's lifespan API for optional warm-loading at startup.

## Standard Stack

The implementation uses existing dependencies plus one small addition.

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| cachetools | 5.x | TTLCache with per-item expiration | De facto standard for Python TTL caching; already widely used |
| torch | (via marker-pdf) | GPU memory management (`empty_cache`, `mps.empty_cache`) | PyTorch's official memory cleanup API |
| threading | stdlib | Lock for thread-safe cache access | Built-in, no dependencies |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| time | stdlib | Monotonic time for TTL tracking | Default timer for TTLCache |
| gc | stdlib | Force garbage collection after model eviction | Memory cleanup helper |
| weakref | stdlib | Optional finalizers for cleanup | Complex lifecycle scenarios |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| cachetools.TTLCache | functools.lru_cache + manual TTL | lru_cache has no per-item TTL; requires wrapper complexity |
| Manual singleton | @st.cache_resource (Streamlit) | Streamlit-specific; not applicable to FastMCP |
| Module-level global | Class-based cache | Globals are harder to test; class allows dependency injection |

**Installation:**
```bash
pip install cachetools
```

Or add to pyproject.toml:
```toml
dependencies = [
    "cachetools>=5.0.0",
    # ... existing deps
]
```

## Architecture Patterns

### Recommended Project Structure

```
src/scholardoc_ocr/
├── model_cache.py      # NEW: Singleton model cache with TTL
├── surya.py            # MODIFY: Add get_cached_models() wrapper
├── pipeline.py         # MODIFY: Use cached models instead of load_models()
├── mcp_server.py       # MODIFY: Add lifespan hook for warm-loading
└── device.py           # EXISTING: Device detection (Phase 12)
```

### Pattern 1: Thread-Safe Singleton Model Cache

**What:** A class that manages model lifecycle with TTL expiration and thread-safe access.
**When to use:** Whenever models need to persist across multiple requests (MCP server, API server).
**Example:**
```python
# Source: cachetools docs + PyTorch memory patterns
import gc
import logging
import threading
import time
from typing import Any

from cachetools import TTLCache

logger = logging.getLogger(__name__)

_CACHE_KEY = "surya_models"

class ModelCache:
    """Singleton cache for Surya/Marker models with TTL eviction."""

    _instance: "ModelCache | None" = None
    _lock = threading.Lock()

    def __init__(self, ttl_seconds: float = 1800.0):  # 30 minutes default
        self._ttl = ttl_seconds
        self._cache: TTLCache[str, tuple[dict[str, Any], str]] = TTLCache(
            maxsize=1, ttl=ttl_seconds
        )
        self._cache_lock = threading.Lock()
        self._load_time: float | None = None

    @classmethod
    def get_instance(cls, ttl_seconds: float = 1800.0) -> "ModelCache":
        """Get or create the singleton instance."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(ttl_seconds)
        return cls._instance

    def get_models(self, device: str | None = None) -> tuple[dict[str, Any], str]:
        """Get cached models or load if not cached/expired."""
        with self._cache_lock:
            cached = self._cache.get(_CACHE_KEY)
            if cached is not None:
                logger.debug("Using cached models (loaded %.1fs ago)",
                             time.monotonic() - (self._load_time or 0))
                return cached

        # Load outside the lock to avoid blocking other threads
        logger.info("Loading models (cache miss or expired)")
        from . import surya

        start = time.monotonic()
        model_dict, device_used = surya.load_models(device=device)
        load_time = time.monotonic() - start
        logger.info("Models loaded in %.1fs on %s", load_time, device_used)

        with self._cache_lock:
            self._cache[_CACHE_KEY] = (model_dict, device_used)
            self._load_time = time.monotonic()

        return model_dict, device_used

    def is_loaded(self) -> bool:
        """Check if models are currently cached."""
        with self._cache_lock:
            return _CACHE_KEY in self._cache

    def evict(self) -> None:
        """Force eviction of cached models and cleanup GPU memory."""
        with self._cache_lock:
            if _CACHE_KEY in self._cache:
                del self._cache[_CACHE_KEY]
                self._load_time = None

        # GPU memory cleanup
        self._cleanup_gpu_memory()
        gc.collect()
        logger.info("Models evicted and GPU memory cleared")

    def _cleanup_gpu_memory(self) -> None:
        """Clear GPU memory caches (CUDA and MPS)."""
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
        except Exception as e:
            logger.warning("GPU memory cleanup failed: %s", e)
```

### Pattern 2: FastMCP Lifespan for Warm Loading

**What:** Use FastMCP's lifespan context manager to pre-load models at server startup.
**When to use:** When you want the first OCR request to be fast (no loading delay).
**Example:**
```python
# Source: FastMCP docs + GitHub discussions
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP

from .model_cache import ModelCache

@asynccontextmanager
async def mcp_lifespan(server: FastMCP):
    """Lifespan hook for model warm-loading."""
    import os

    warm_load = os.environ.get("SCHOLARDOC_WARM_LOAD", "false").lower() == "true"

    if warm_load:
        # Pre-load models during startup
        cache = ModelCache.get_instance()
        cache.get_models()  # Triggers load

    yield  # Server runs

    # Cleanup on shutdown
    cache = ModelCache.get_instance()
    cache.evict()

mcp = FastMCP("scholardoc-ocr", lifespan=mcp_lifespan)
```

### Pattern 3: Inter-Document Memory Cleanup

**What:** Clear GPU memory between documents without evicting the model cache.
**When to use:** After each document to prevent VRAM accumulation across a batch.
**Example:**
```python
# Source: PyTorch FAQ OOM patterns
def cleanup_between_documents() -> None:
    """Release unused GPU memory without unloading models."""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
    except ImportError:
        pass
    gc.collect()
```

### Pattern 4: Memory Profiling Accessors

**What:** Expose VRAM usage information via an API or logs.
**When to use:** For debugging and monitoring production deployments.
**Example:**
```python
# Source: PyTorch memory profiling docs
def get_memory_stats() -> dict:
    """Return current GPU memory usage statistics."""
    stats = {"device": "unknown", "allocated_mb": 0, "reserved_mb": 0}

    try:
        import torch
        if torch.cuda.is_available():
            stats["device"] = "cuda"
            stats["allocated_mb"] = torch.cuda.memory_allocated() / 1024 / 1024
            stats["reserved_mb"] = torch.cuda.memory_reserved() / 1024 / 1024
        elif torch.backends.mps.is_available():
            stats["device"] = "mps"
            # MPS has limited memory introspection
            stats["allocated_mb"] = torch.mps.current_allocated_memory() / 1024 / 1024
    except Exception:
        pass

    return stats
```

### Anti-Patterns to Avoid

- **Loading models in tool functions:** Each `@mcp.tool()` call would reload models; use the singleton cache instead.
- **Global module-level model loading:** Triggers import-time loading; use lazy initialization.
- **Calling `empty_cache()` after every tensor operation:** Causes fragmentation; call only between documents or on eviction.
- **Ignoring thread safety:** Multiple concurrent MCP requests can cause race conditions; always use locks.
- **TTL that's too short:** Setting TTL < 5 minutes causes frequent reloads; 30 minutes is a reasonable default.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TTL cache with expiration | Custom dict + timestamps | cachetools.TTLCache | Handles edge cases (thread safety, lazy expiration) |
| Thread-safe singleton | Manual locking | Double-checked locking pattern or `threading.Lock` | Race conditions are subtle |
| GPU memory cleanup | Manual tensor tracking | `torch.cuda.empty_cache()` / `torch.mps.empty_cache()` | Interacts correctly with PyTorch allocator |
| Memory profiling | nvidia-smi parsing | `torch.cuda.memory_allocated()` | Programmatic access, no subprocess |

**Key insight:** Model caching appears simple but has subtle concurrency and memory management challenges. Using established patterns prevents memory leaks and race conditions.

## Common Pitfalls

### Pitfall 1: Loading Models Inside Exception Handler

**What goes wrong:** GPU memory isn't freed when catching OOM and retrying.
**Why it happens:** Python exception object holds reference to stack frame, preventing GC of tensors in local variables.
**How to avoid:** Set a flag in except block, handle recovery OUTSIDE the except block (already implemented in Phase 12).
**Warning signs:** Memory usage stays high after OOM, subsequent operations also fail.

### Pitfall 2: TTL Expiration During Active Inference

**What goes wrong:** Models get evicted while a long-running inference is in progress.
**Why it happens:** TTLCache checks expiration on access, not during use.
**How to avoid:** Use a lock that prevents eviction during active use, or set TTL longer than expected inference time.
**Warning signs:** Random failures on long documents, "model not found" errors mid-processing.

### Pitfall 3: Concurrent Model Loading Race

**What goes wrong:** Two requests both see cache miss and both load models, wasting memory.
**Why it happens:** Check-then-act race condition without proper locking.
**How to avoid:** Acquire lock before checking cache, load while holding lock (or use per-key locking).
**Warning signs:** Double memory usage, duplicate model loading logs.

### Pitfall 4: MPS Memory Not Actually Freed

**What goes wrong:** `torch.mps.empty_cache()` doesn't seem to reduce memory usage.
**Why it happens:** MPS memory reporting is less accurate than CUDA; memory may be fragmented.
**How to avoid:** Accept that MPS memory management is less predictable; test with real workloads.
**Warning signs:** Activity Monitor shows high memory even after cleanup.

### Pitfall 5: Stale Models After PyTorch Update

**What goes wrong:** Cached models become incompatible after library update.
**Why it happens:** In-memory model objects may use internal state that changes between versions.
**How to avoid:** Include library version in cache key, or evict on server restart.
**Warning signs:** Cryptic errors during inference, shape mismatches.

## Code Examples

Verified patterns from official sources:

### Integration with Existing Pipeline

```python
# In pipeline.py, replace:
# model_dict, device_used = surya.load_models()

# With:
from .model_cache import ModelCache

cache = ModelCache.get_instance()
model_dict, device_used = cache.get_models()

# After processing each file (between documents):
from .model_cache import cleanup_between_documents
cleanup_between_documents()
```

### MCP Server Warm Loading

```python
# In mcp_server.py
import os
from contextlib import asynccontextmanager

from .model_cache import ModelCache

@asynccontextmanager
async def mcp_lifespan(server):
    """Optional model pre-loading at startup."""
    if os.environ.get("SCHOLARDOC_WARM_LOAD", "false").lower() == "true":
        ttl = float(os.environ.get("SCHOLARDOC_MODEL_TTL", "1800"))
        cache = ModelCache.get_instance(ttl_seconds=ttl)
        cache.get_models()

    yield

    # Cleanup on shutdown
    ModelCache.get_instance().evict()

# Update mcp initialization:
mcp = FastMCP("scholardoc-ocr", lifespan=mcp_lifespan)
```

### Memory Stats Tool for MCP

```python
# Add to mcp_server.py
@mcp.tool()
async def ocr_memory_stats() -> dict:
    """Get current GPU memory usage and model cache status.

    Returns memory statistics for debugging and monitoring.
    """
    from .model_cache import ModelCache, get_memory_stats

    cache = ModelCache.get_instance()
    memory = get_memory_stats()

    return {
        "models_loaded": cache.is_loaded(),
        "device": memory["device"],
        "allocated_mb": round(memory["allocated_mb"], 2),
        "reserved_mb": round(memory["reserved_mb"], 2),
    }
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Load models per request | Singleton cache with TTL | Best practice 2024+ | 30-60s savings on subsequent requests |
| Global module-level models | Lazy loading with lifespan hooks | FastMCP pattern | Faster server startup when warm-load disabled |
| Manual memory tracking | `torch.cuda.memory_allocated()` | PyTorch 1.4+ | Accurate VRAM monitoring |
| Per-request GPU cleanup | Between-document cleanup only | Best practice | Reduced overhead while preventing accumulation |

**Deprecated/outdated:**
- `CUDA_VISIBLE_DEVICES=""` for CPU forcing: Use `device="cpu"` parameter instead
- `torch.cuda.empty_cache()` called after every operation: Causes fragmentation, use sparingly

## Open Questions

Things that couldn't be fully resolved:

1. **Optimal TTL Value**
   - What we know: 30 minutes is a common default; prevents stale models while avoiding reload overhead
   - What's unclear: What's the actual memory cost of keeping models loaded vs. user experience of cold starts?
   - Recommendation: Make TTL configurable via environment variable, default to 30 minutes, monitor in production

2. **MPS Memory Introspection Accuracy**
   - What we know: `torch.mps.current_allocated_memory()` exists but may not reflect true Metal memory usage
   - What's unclear: How accurate is this for production monitoring? Does macOS report differently?
   - Recommendation: Implement the API but document its limitations; VRAM profiling on MPS is best-effort

3. **FastMCP Lifespan Stability**
   - What we know: FastMCP 2.0 changed lifespan patterns; some issues reported with lifespan running per-request
   - What's unclear: Is the current FastMCP version in use stable for lifespan hooks?
   - Recommendation: Test lifespan behavior thoroughly; have fallback to lazy loading if issues arise

4. **Multiple Device Support**
   - What we know: Current cache is keyed by a single key regardless of device
   - What's unclear: Should we support caching models for multiple devices (CPU + MPS)?
   - Recommendation: Start with single device (auto-detected); multi-device caching adds complexity without clear benefit

## Sources

### Primary (HIGH confidence)

- **cachetools documentation** (https://cachetools.readthedocs.io/) - TTLCache API, thread safety guidance
- **PyTorch Memory Management FAQ** (https://pytorch.org/docs/stable/notes/faq.html) - OOM handling, empty_cache() usage
- **PyTorch CUDA Memory Documentation** (https://docs.pytorch.org/docs/stable/generated/torch.cuda.memory.empty_cache.html) - Official empty_cache behavior
- **Project code: tests/benchmarks/conftest.py** - Existing session-scoped model loading pattern

### Secondary (MEDIUM confidence)

- **FastMCP GitHub Discussions #1763** (https://github.com/jlowin/fastmcp/discussions/1763) - Lifespan hook patterns for FastMCP 2.0
- **FastMCP Server Documentation** (https://gofastmcp.com/python-sdk/fastmcp-server-server) - Server lifecycle management
- **Model Warmup Best Practices** (https://medium.com/better-ml/model-warmup-8e9681ef4d41) - Why warmup matters for inference servers

### Tertiary (LOW confidence)

- **WebSearch: MPS memory profiling** - Limited authoritative sources on MPS memory introspection
- **WebSearch: Python singleton patterns** - General patterns, not ML-specific

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - cachetools and PyTorch memory APIs are well-documented
- Architecture: MEDIUM - FastMCP lifespan needs testing; singleton pattern is established
- Pitfalls: HIGH - OOM handling and threading pitfalls are well-documented
- Memory profiling: MEDIUM - CUDA well-documented, MPS less so

**Research date:** 2026-02-04
**Valid until:** 2026-03-04 (30 days - stable domain, but FastMCP may evolve)

---

## Implementation Notes for Planner

### Critical Success Criteria Mapping

| Success Criterion | Implementation Approach |
|-------------------|------------------------|
| 1. Second request without 30-60s delay | ModelCache singleton returns cached models |
| 2. TTL-based auto-eviction (default 30 min) | cachetools.TTLCache with configurable TTL |
| 3. Memory cleanup between documents | `cleanup_between_documents()` after each file |
| 4. Warm pool on startup (configurable) | FastMCP lifespan + `SCHOLARDOC_WARM_LOAD` env var |
| 5. VRAM profiling via API/logs | `get_memory_stats()` + `ocr_memory_stats` MCP tool |

### Environment Variables to Support

| Variable | Default | Purpose |
|----------|---------|---------|
| `SCHOLARDOC_WARM_LOAD` | `false` | Enable model pre-loading at startup |
| `SCHOLARDOC_MODEL_TTL` | `1800` | Cache TTL in seconds (30 minutes) |

### File Changes Required

1. **NEW: `model_cache.py`** - ModelCache class, cleanup functions, memory stats
2. **MODIFY: `surya.py`** - Add `get_cached_models()` wrapper (optional, for API consistency)
3. **MODIFY: `pipeline.py`** - Use ModelCache instead of direct `load_models()` for MCP server path
4. **MODIFY: `mcp_server.py`** - Add lifespan hook, `ocr_memory_stats` tool
5. **NEW: `tests/test_model_cache.py`** - Unit tests for cache behavior

### Dependencies to Add

```toml
# pyproject.toml
dependencies = [
    "cachetools>=5.0.0",
    # ... existing
]
```
