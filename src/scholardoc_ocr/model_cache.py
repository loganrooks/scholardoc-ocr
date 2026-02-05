"""Thread-safe model caching with TTL-based expiration and GPU memory management.

This module provides caching infrastructure to eliminate repeated model loading
delays between requests. Models are cached in memory with configurable TTL
(default 30 minutes) and thread-safe access.

All torch imports are lazy (inside function bodies) to avoid loading ML
dependencies at module import time.
"""

from __future__ import annotations

import gc
import logging
import os
import threading
import time
from typing import Any

from cachetools import TTLCache

logger = logging.getLogger(__name__)


class ModelCache:
    """Thread-safe singleton cache for Surya/Marker models with TTL expiration.

    The cache holds at most one model set (maxsize=1) and automatically expires
    entries after the configured TTL (default 30 minutes). Thread safety is
    ensured via double-checked locking for singleton instantiation and a
    separate lock for cache operations.

    Environment Variables:
        SCHOLARDOC_MODEL_TTL: Override default TTL in seconds (default: 1800.0)

    Example:
        >>> cache = ModelCache.get_instance()
        >>> models, device = cache.get_models()  # Loads on first call
        >>> models2, device2 = cache.get_models()  # Returns cached
        >>> cache.evict()  # Force eviction and GPU cleanup
    """

    _instance: ModelCache | None = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self, ttl_seconds: float = 1800.0) -> None:
        """Initialize the cache with given TTL.

        Note: Use get_instance() instead of direct instantiation.

        Args:
            ttl_seconds: Time-to-live for cached models in seconds.
        """
        self._cache: TTLCache[str, tuple[dict[str, Any], str]] = TTLCache(
            maxsize=1, ttl=ttl_seconds
        )
        self._cache_lock = threading.Lock()
        self._load_time: float | None = None
        self._ttl = ttl_seconds
        logger.debug("ModelCache initialized with TTL=%s seconds", ttl_seconds)

    @classmethod
    def get_instance(cls, ttl_seconds: float = 1800.0) -> ModelCache:
        """Get or create the singleton ModelCache instance.

        Thread-safe via double-checked locking pattern.

        Args:
            ttl_seconds: Time-to-live for cached models in seconds.
                Only used on first call; subsequent calls ignore this.
                Can be overridden by SCHOLARDOC_MODEL_TTL environment variable.

        Returns:
            The singleton ModelCache instance.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    # Check for environment variable override
                    env_ttl = os.environ.get("SCHOLARDOC_MODEL_TTL")
                    if env_ttl is not None:
                        try:
                            ttl_seconds = float(env_ttl)
                            logger.info(
                                "Using TTL from SCHOLARDOC_MODEL_TTL: %s seconds", ttl_seconds
                            )
                        except ValueError:
                            logger.warning(
                                "Invalid SCHOLARDOC_MODEL_TTL value '%s', using default", env_ttl
                            )
                    cls._instance = cls(ttl_seconds)
        return cls._instance

    def get_models(self, device: str | None = None) -> tuple[dict[str, Any], str]:
        """Get cached models or load fresh if cache miss or expired.

        Thread-safe: model loading happens outside the lock to avoid blocking
        other threads. Race conditions on cache miss result in potentially
        loading models twice, but only the first result is cached.

        Args:
            device: Optional device string (e.g. "cpu", "cuda", "mps").
                If None, auto-detects the best available device.

        Returns:
            Tuple of (model_dict, device_used_str).
        """
        cache_key = "models"

        # Fast path: check cache under lock
        with self._cache_lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                logger.debug("Cache hit, returning cached models (device=%s)", cached[1])
                return cached

        # Cache miss: load models outside lock to avoid blocking
        logger.info("Cache miss, loading models (device=%s)", device)
        from . import surya  # noqa: PLC0415

        model_dict, device_used = surya.load_models(device)
        load_time = time.time()

        # Store in cache under lock
        with self._cache_lock:
            # Another thread may have populated cache while we were loading
            if cache_key not in self._cache:
                self._cache[cache_key] = (model_dict, device_used)
                self._load_time = load_time
                logger.info("Models cached (device=%s)", device_used)
            else:
                # Use already-cached version, discard our load
                logger.debug("Another thread cached models first, using those")
                return self._cache[cache_key]

        return model_dict, device_used

    def is_loaded(self) -> bool:
        """Check if models are currently cached (not expired).

        Returns:
            True if models are cached and not expired.
        """
        with self._cache_lock:
            return "models" in self._cache

    def evict(self) -> None:
        """Force eviction of cached models and cleanup GPU memory.

        Call this to free GPU memory when models are no longer needed.
        """
        with self._cache_lock:
            if "models" in self._cache:
                del self._cache["models"]
                self._load_time = None
                logger.info("Models evicted from cache")

        self._cleanup_gpu_memory()

    def _cleanup_gpu_memory(self) -> None:
        """Clear GPU memory caches (MPS and CUDA).

        This is an internal helper called after eviction.
        """
        try:
            import torch  # noqa: PLC0415

            if torch.backends.mps.is_available():
                torch.mps.empty_cache()
                logger.debug("MPS cache cleared")
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                logger.debug("CUDA cache cleared")
        except ImportError:
            logger.debug("torch not available, skipping GPU cleanup")
        except Exception as exc:
            logger.warning("GPU cleanup failed: %s", exc)

        gc.collect()


def cleanup_between_documents() -> None:
    """Clear unused GPU memory between document processing.

    Call this between documents to free intermediate GPU memory while
    keeping the model cache intact. This helps prevent OOM errors on
    long-running batch jobs.

    Does NOT evict the model cache - models remain loaded for fast
    subsequent inference.
    """
    try:
        import torch  # noqa: PLC0415

        if torch.backends.mps.is_available():
            torch.mps.empty_cache()
            logger.debug("MPS cache cleared between documents")
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.debug("CUDA cache cleared between documents")
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("GPU cleanup between documents failed: %s", exc)

    gc.collect()


def get_memory_stats() -> dict[str, Any]:
    """Get current GPU memory statistics.

    Returns:
        Dict with keys:
        - device: str - "mps", "cuda", or "unknown"
        - allocated_mb: float - Currently allocated memory in MB
        - reserved_mb: float - Reserved memory in MB (CUDA only, 0 for MPS)

    Note: Returns zeros if torch is not available or no GPU is detected.
    """
    result: dict[str, Any] = {
        "device": "unknown",
        "allocated_mb": 0.0,
        "reserved_mb": 0.0,
    }

    try:
        import torch  # noqa: PLC0415

        if torch.backends.mps.is_available():
            result["device"] = "mps"
            # MPS memory API returns bytes
            allocated = torch.mps.current_allocated_memory()
            result["allocated_mb"] = allocated / (1024 * 1024)
            # MPS doesn't have reserved memory concept
            result["reserved_mb"] = 0.0
        elif torch.cuda.is_available():
            result["device"] = "cuda"
            # CUDA memory API returns bytes
            result["allocated_mb"] = torch.cuda.memory_allocated() / (1024 * 1024)
            result["reserved_mb"] = torch.cuda.memory_reserved() / (1024 * 1024)
        else:
            result["device"] = "cpu"
    except ImportError:
        logger.debug("torch not available for memory stats")
    except Exception as exc:
        logger.warning("Failed to get memory stats: %s", exc)

    return result
