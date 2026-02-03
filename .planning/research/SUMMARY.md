# Project Research Summary

**Project:** scholardoc-ocr v2.1 Performance Milestone
**Domain:** OCR Pipeline Performance Optimization (Apple Silicon / MPS)
**Researched:** 2026-02-03
**Confidence:** HIGH

## Executive Summary

The scholardoc-ocr v2.1 performance milestone focuses on optimizing Surya OCR performance on Apple Silicon through MPS (Metal Performance Shaders) acceleration. Research reveals that the primary performance bottleneck is not lack of GPU acceleration but architectural inefficiencies: sequential per-file Surya processing, missing batch size configuration, and no model caching for the MCP server. The existing stack already supports MPS auto-detection; the work ahead is configuration tuning and architectural restructuring.

The recommended approach prioritizes quick wins (explicit MPS device selection, batch size environment variables) followed by high-impact architectural changes (cross-file page batching, model caching). No new production dependencies are required. Development tooling (pytest-benchmark, memray, hyperfine) will validate optimizations and prevent regressions. Expected cumulative performance improvement: 5-15x for multi-file batches.

Critical risks center on PyTorch/MPS-specific pitfalls: fork-corrupting GPU state, benchmarking without synchronization showing false results, MPS memory leaks in long-running servers, and silent CPU fallback for unsupported operations. Prevention requires strict architectural discipline (spawn context for workers, never initialize PyTorch before ProcessPoolExecutor), proper benchmarking methodology (torch.mps.synchronize() before timing), and system-level memory monitoring (not just PyTorch's view). MPS has known bugs (TableRecEncoderDecoderModel falls back to CPU, text detection issues) that must be understood and worked around.

## Key Findings

### Recommended Stack

**No new production dependencies required.** PyTorch MPS backend is already available through marker-pdf's transitive dependencies. The gap is not "enable MPS" but "optimize for MPS" through configuration tuning and architectural changes. Current Surya integration accepts device parameters but defaults to auto-detection, which works but isn't optimized for Apple Silicon's unified memory architecture.

**Core technologies:**
- **PyTorch MPS (via marker-pdf)** — GPU acceleration on Apple Silicon — Already bundled, just needs explicit device selection and batch size tuning
- **pytest-benchmark** — Statistical performance testing — Integrated with existing pytest, enables before/after comparisons and regression detection
- **memray** — Memory profiling with native allocation tracking — Critical for PyTorch memory analysis (models live in C++ extensions), generates flame graphs
- **hyperfine** — End-to-end CLI benchmarking — Shell-level timing with statistical outlier detection, validates real-world performance

**Optional additions:**
- **safetensors >=0.7.0** — Memory-mapped model loading to reduce 2x memory spike during load (verify marker-pdf doesn't already use it)

**Environment variables for tuning:**
- `TORCH_DEVICE=mps` — Force MPS device
- `RECOGNITION_BATCH_SIZE` — Default GPU: 512, recommended MPS: 256-384
- `DETECTOR_BATCH_SIZE` — Default GPU: 36, recommended MPS: 18-48
- `PYTORCH_ENABLE_MPS_FALLBACK=1` — Allow CPU fallback for unsupported ops
- `PYTORCH_MPS_HIGH_WATERMARK_RATIO` — Memory pressure threshold (default 1.0, recommend 0.7 for development)

### Expected Features

**Must have (table stakes):**
- **Explicit MPS device selection** — Auto-detection works but explicit device ensures correct GPU usage and clearer error messages
- **Pass batch_size to Marker converter** — SuryaConfig has batch_size=50 but convert_pdf ignores it; must set RECOGNITION_BATCH_SIZE/DETECTOR_BATCH_SIZE env vars
- **VRAM-aware batch sizing** — Apple Silicon unified memory allows larger batches than discrete GPUs; must tune per chip (M1: 16GB, M2 Pro/Max: 32-96GB)
- **Model warm-up on first load** — First inference is 2-5x slower due to kernel compilation; run dummy page during "loading models" to hide latency
- **Cross-file page batching** — Current: 3 files x 10 pages = 3 separate Surya jobs; optimal: 1 batch of 30 pages mapped back to files

**Should have (differentiators):**
- **Surya model compilation** — `COMPILE_DETECTOR=true` enables torch.compile for 20-40% speedup but only worthwhile for 50+ page jobs (30-60s cold start cost)
- **Memory pool optimization** — Reduce fragmentation with torch.mps.empty_cache() between files, not between pages
- **Adaptive batch sizing** — Dense text pages need more memory than sparse pages; adjust batch size dynamically based on page complexity
- **Progressive result streaming** — Return Surya results as pages complete rather than waiting for entire batch (enables early partial results for MCP)
- **Model unloading after Surya phase** — Explicit cleanup of ~5GB models after Phase 2 via del + torch.mps.empty_cache()
- **Parallel Tesseract + Surya preparation** — Pre-load Surya models on GPU during Phase 1 CPU work, reducing perceived wait time by 10-20s

**Defer (v2+):**
- **torch.compile on MPS** — Enable via env var for power users, default OFF (only beneficial for 100+ page batches, experimental MPS support)
- **Custom CUDA kernels** — Surya/Marker are pure PyTorch; custom kernels break on updates, don't work on MPS
- **Dynamic batch size changes mid-job** — Requires new converter instance with full model reload; optimize for full job instead
- **Aggressive memory cleanup** — torch.mps.empty_cache() between every page adds overhead; only cleanup between files or at memory limits

**Anti-features (explicitly avoid):**
- **Multiprocessing for Surya** — MPS cannot share GPU tensors across processes; Marker explicitly errors on this
- **CPU fallback for "small" jobs** — Even 2-page jobs benefit from GPU (10-50x faster); auto-CPU wastes user time
- **torch.compile by default** — Compilation overhead exceeds runtime savings for typical 5-20 page academic PDFs

### Architecture Approach

The existing pipeline uses two-phase orchestration: parallel Tesseract (Phase 1) followed by sequential per-file Surya (Phase 2). The performance bottleneck is Phase 2's sequential file processing and lack of model caching. The recommended architecture introduces three new components while preserving the existing two-phase structure.

**Major components:**
1. **ModelManager (model_cache.py)** — Singleton managing Surya model lifecycle with TTL-based eviction; enables model sharing across MCP requests without memory leaks
2. **Cross-File Batch Processor (batch.py)** — Aggregates flagged pages across all files into single Surya job, then maps results back to source files; eliminates sequential per-file processing
3. **Device Configuration (device.py)** — Explicit device detection with MPS validation; provides torch.device("mps") instead of auto-detection
4. **Benchmarking Infrastructure (benchmarks/)** — pytest-benchmark fixtures for model loading, batch processing, device comparison, and end-to-end pipeline timing

**Key architectural changes:**
- Phase 2 changes from "for each file: load models, process" to "collect all pages, load models once, batch process, distribute results"
- MCP server maintains warm model cache across requests (30-60s model load happens once, not per request)
- ProcessPoolExecutor continues for Tesseract (CPU-bound), but Surya remains single-threaded in main process (GPU-bound)
- Device selection happens before model loading; explicit spawn context prevents fork-corrupting GPU state

**Data flow transformation:**
```
BEFORE: File1 → Surya → Result1, File2 → Surya → Result2, File3 → Surya → Result3
AFTER:  File1,File2,File3 → Aggregate → Single Surya Batch → Distribute → Results1,2,3
```

### Critical Pitfalls

**From V3 (MPS/Performance-Specific):**

1. **ProcessPoolExecutor with Fork Corrupts MPS/CUDA State (#24)** — If PyTorch/MPS is initialized before forking ProcessPoolExecutor workers, child processes inherit corrupted GPU state causing silent failures. Prevention: Use explicit spawn context, never initialize PyTorch before pool creation, add defensive assert before spawning workers.

2. **Benchmarking Without GPU Synchronization Shows Wrong Times (#25)** — GPU operations are asynchronous; time.time() shows CPU dispatch time, not computation time. Without torch.mps.synchronize(), benchmarks show 10x speedup that doesn't exist. Prevention: Always call torch.mps.synchronize() before reading timing, use torch.utils.benchmark.Timer (handles sync automatically), include 5-10 warmup iterations.

3. **MPS TableRecEncoderDecoderModel Falls Back to CPU Silently (#26)** — Marker's table recognition model is incompatible with MPS and silently falls back to CPU (10-30x slower). Prevention: Audit which models actually use MPS via profiling, disable table processing for non-table documents, log actual device per model.

4. **MPS Memory Leaks in Long-Running Processes (#27)** — MPS backend has known memory leaks that compound over thousands of operations in MCP server. Prevention: Call torch.mps.empty_cache() + gc.collect() between documents (not pages), monitor both torch.mps.current_allocated_memory() AND process RSS, implement watchdog to restart server if memory exceeds threshold.

5. **Batch Size Tuning Ignores MPS Memory Constraints (#28)** — Copying CUDA batch size recommendations (864) causes system slowdown due to memory pressure on unified memory (no discrete VRAM). Prevention: Start conservative (8GB: batch 16-32, 16GB: batch 32-64, 32GB+: batch 64-128), implement adaptive sizing, monitor Activity Monitor's "Memory Pressure" graph.

**From V1/V2 (General Pipeline):**

6. **CPU Oversubscription in Nested Parallelism (#3)** — ProcessPoolExecutor spawns N processes, each running ocrmypdf with internal threading. Prevention: Cap jobs_per_file when running multiple files, treat total CPU budget as shared.

7. **Logging from ProcessPoolExecutor Workers Silently Lost (#14)** — Workers inherit NO logging configuration with spawn start method (macOS default). Prevention: Use QueueHandler in workers with Manager().Queue(), QueueListener in main process.

8. **FastMCP Server Crash on Client Timeout During OCR (#15)** — MCP client timeout during long OCR causes server crash instead of graceful cancellation. Prevention: Use FastMCP task=True protocol-native background tasks (v2.14+), set request_timeout, send progress notifications to keep connection alive.

## Implications for Roadmap

Based on research, the performance optimization work naturally divides into four phases, ordered by dependencies and risk:

### Phase 1: Device Configuration Foundation
**Rationale:** Low-risk foundation enabling MPS testing without changes to core pipeline. Must establish correct device selection before any optimization work. Quick wins with immediate performance improvement (2-5x expected).

**Delivers:**
- device.py module with MPS detection and validation
- Explicit torch.device("mps") selection in load_models()
- SCHOLARDOC_DEVICE environment variable support
- RECOGNITION_BATCH_SIZE and DETECTOR_BATCH_SIZE configuration via env vars
- Model warm-up routine (single dummy page after load)
- Device info in logging output

**Addresses (from FEATURES.md):**
- Explicit MPS device selection (table stakes)
- Pass batch_size to Marker converter (table stakes)
- Model warm-up on first load (table stakes)
- VRAM-aware batch sizing (table stakes)

**Avoids (from PITFALLS.md):**
- #24: Fork corrupts GPU state (verify spawn context, no PyTorch init before pool)
- #25: Benchmarking without synchronization (establish correct methodology)
- #32: Float64 operations crash (force float32 default)

**Research Flag:** Standard patterns, skip research-phase. PyTorch MPS documentation is comprehensive.

### Phase 2: Model Caching for MCP Server
**Rationale:** Highest impact on MCP server performance (eliminates 30-60s model load per request). Independent of batching changes, can be developed in parallel. Critical for long-running server deployment.

**Delivers:**
- model_cache.py module with ModelManager singleton
- Thread-safe model access with TTL eviction
- Modified surya.py to use cache by default
- Updated mcp_server.py to share models across requests
- Model preload option for server startup
- Memory cleanup between requests

**Addresses (from FEATURES.md):**
- Model unloading after Surya phase (differentiator)
- Memory pool optimization (differentiator)

**Avoids (from PITFALLS.md):**
- #27: MPS memory leaks in long-running processes (empty_cache + gc.collect)
- #29: Model loading time dominates small docs (warm model pool)
- #35: Unified memory accounting confusion (system-level monitoring)

**Research Flag:** Standard patterns, skip research-phase. Singleton caching is well-documented pattern.

### Phase 3: Cross-File Batch Processing
**Rationale:** Most complex change, highest cumulative impact (2-3x additional speedup on top of Phase 1). Benefits from stable model caching. Requires significant pipeline restructure but isolated to Phase 2 orchestration.

**Delivers:**
- batch.py module with BatchJob, PageReference, collect_flagged_pages(), process_batch()
- Page aggregation across all files before Surya call
- Single temp PDF with all flagged pages
- Result mapping back to source files (per-file, per-page dictionary)
- Modified pipeline.py to use batch processing for Phase 2
- Integration tests with multi-file batches

**Addresses (from FEATURES.md):**
- Cross-file page batching (table stakes, highest impact)
- Adaptive batch sizing based on page complexity (differentiator)

**Avoids (from PITFALLS.md):**
- #4: Fragile index-based page mapping (explicit page identifiers, not positional)
- #20: Work directory collision between concurrent runs (UUID-based work dirs)
- #26: TableRec falls back to CPU silently (audit actual device usage)

**Research Flag:** May need deeper research during planning for optimal temp PDF creation strategy and result distribution mapping logic. PyMuPDF page extraction patterns are well-documented but complex.

### Phase 4: Benchmarking Infrastructure
**Rationale:** Validates Phases 1-3, catches regressions, provides objective performance metrics. Should be developed last so benchmarks test optimized code, not original implementation.

**Delivers:**
- pytest-benchmark dependency in pyproject.toml dev extras
- perf optional dependency group (benchmark + memray)
- benchmarks/ directory with fixtures and sample data
- Benchmark categories: model loading (cold vs cached), batch processing (pages/sec at different batch sizes), device comparison (CPU vs MPS), end-to-end pipeline
- scripts/benchmark.sh using hyperfine for CLI-level comparison
- CI integration for regression detection

**Addresses (from FEATURES.md):**
- Progressive result streaming (deferred to v2+, but benchmark establishes baseline)

**Avoids (from PITFALLS.md):**
- #25: Benchmarking without GPU synchronization (establish correct methodology)
- #34: Warmup iterations counted in benchmarks (5-10 warmup before timing)
- #36: HuggingFace model downloads during processing (pre-download in setup)

**Research Flag:** Standard patterns, skip research-phase. pytest-benchmark and hyperfine documentation is comprehensive.

### Phase Ordering Rationale

1. **Device Configuration first:** Foundation for all other work. Low risk, immediate gains. Validates MPS functionality before complex changes.

2. **Model Caching second:** High value, independent of batching. Can be developed in parallel with Phase 3 planning. Critical for MCP server production use.

3. **Cross-File Batching third:** Most complex, highest impact. Benefits from stable device configuration and model caching. Isolated to Phase 2 orchestration preserves existing Tesseract parallelism.

4. **Benchmarking fourth:** Validates previous phases, prevents regressions. Testing optimized code is more valuable than benchmarking original implementation.

This ordering avoids pitfalls by:
- Establishing correct GPU state management (spawn context, device selection) before optimization work
- Validating MPS functionality on simple cases before complex batch processing
- Building model lifecycle management before memory-intensive batching
- Developing benchmarking methodology alongside implementation, not retroactively

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 3 (Cross-File Batching):** PyMuPDF page extraction and insertion patterns need detailed exploration. Result mapping logic (distributed Surya output back to per-file results) requires careful design to avoid fragile index-based mapping pitfall #4.

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (Device Configuration):** PyTorch device selection is well-documented, env var configuration is standard Python pattern
- **Phase 2 (Model Caching):** Singleton pattern with TTL is standard ML serving pattern, extensively documented in Streamlit/FastAPI guides
- **Phase 4 (Benchmarking):** pytest-benchmark and hyperfine have comprehensive documentation, methodology is well-established

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyTorch MPS backend verified in official docs, Surya batch size env vars verified in GitHub README, memray/pytest-benchmark verified on PyPI |
| Features | HIGH | Current codebase analysis shows exact gaps (SuryaConfig.batch_size unused, sequential per-file Surya), expected performance improvements grounded in research (5-15x cumulative) |
| Architecture | HIGH | Proposed components (ModelManager, batch.py, device.py) are standard patterns adapted to existing pipeline structure, minimal disruption to proven Tesseract parallelism |
| Pitfalls | HIGH | V3 MPS pitfalls sourced from PyTorch official docs, Apple Developer guides, and deep-dive blog posts with reproducible examples; V1/V2 pitfalls grounded in actual codebase bugs |

**Overall confidence:** HIGH

All four research documents converge on the same recommendation: the stack already supports MPS, the work is architectural restructuring and configuration tuning. No speculative dependencies or uncertain approaches. The pitfalls are well-documented in PyTorch/Apple ecosystem, not edge cases from sparse community reports.

### Gaps to Address

1. **safetensors usage in marker-pdf:** LOW priority — Research suggests safetensors may already be used by marker-pdf (verify with `pip show marker-pdf` and check dependencies). If not present, evaluate whether 2x memory spike during model load is actually a problem in practice before adding dependency.

2. **torch.compile MPS support:** MEDIUM priority — Research shows torch.compile has limited MPS support as of PyTorch 2.10. This may improve in future PyTorch versions. Document as power-user option via env var (COMPILE_DETECTOR, COMPILE_LAYOUT) but don't enable by default. Re-evaluate in PyTorch 3.0+ release notes.

3. **MPS text detection bug workaround:** HIGH priority during Phase 1 validation — Research mentions Surya text detection has Apple-side bugs on MPS. Must test on target hardware (M1/M2/M3) to determine if CPU fallback is needed specifically for detection model. May need per-model device configuration (detection on CPU, recognition on MPS).

4. **Adaptive batch sizing heuristic:** MEDIUM priority for Phase 3 — Research suggests dense text pages need more memory than sparse pages. Need to develop heuristic (image size / text density estimate) and test whether adaptive sizing provides meaningful benefit vs fixed batch size based on worst-case page.

## Sources

### Primary (HIGH confidence)
- [PyTorch MPS Backend Documentation](https://docs.pytorch.org/docs/stable/notes/mps.html) — MPS device usage, limitations, synchronization, memory management
- [Apple Developer: Accelerated PyTorch Training on Mac](https://developer.apple.com/metal/pytorch/) — Unified memory benefits, MPS setup, Metal integration
- [Surya OCR GitHub README](https://github.com/datalab-to/surya) — RECOGNITION_BATCH_SIZE, DETECTOR_BATCH_SIZE, COMPILE_* env vars, device configuration
- [Marker PDF GitHub Repository](https://github.com/datalab-to/marker) — PdfConverter API, batch processing, MPS fallback configuration
- [pytest-benchmark Documentation](https://pytest-benchmark.readthedocs.io/) — Benchmark fixtures, statistical analysis, --benchmark-compare
- [memray Documentation](https://bloomberg.github.io/memray/) — Memory profiling, native tracking, flame graphs
- [PyTorch Multiprocessing Best Practices](https://docs.pytorch.org/docs/stable/notes/multiprocessing.html) — Fork safety, spawn context, GPU state corruption
- [PyTorch Benchmark Tutorial](https://docs.pytorch.org/tutorials/recipes/recipes/benchmark.html) — Proper timing methodology, warmup, synchronization
- Current codebase analysis (pipeline.py, surya.py, processor.py, mcp_server.py) — Exact gaps identified: sequential per-file Surya, batch_size unused, no model caching

### Secondary (MEDIUM confidence)
- [Elana Simon: The bug that taught me more about PyTorch than years of using it](https://elanapearl.github.io/blog/2025/the-bug-that-taught-me-pytorch/) — Non-contiguous tensor bug deep dive, macOS version requirements
- [PyTorch GitHub Issue #167679](https://github.com/pytorch/pytorch/issues/167679) — macOS 26.0 MPS availability bug (fixed in 26.1)
- [PyTorch MPS Memory Leak Issues](https://github.com/pytorch/pytorch/issues/154329) — SDPA float32 leak, clip_grad_norm_ issues
- [Marker Issue #875: 30x slower than Tesseract](https://github.com/datalab-to/marker/issues/875) — Version regression on Apple Silicon, batch size impact
- [Surya Issue #207: MacBook M1 performance](https://github.com/VikParuchuri/surya/issues/207) — MPS batch size tuning, memory pressure on 8GB machines
- [Streamlit Caching Guide](https://docs.streamlit.io/develop/concepts/architecture/caching) — Singleton pattern for ML models, TTL-based eviction

### Tertiary (LOW confidence)
- WebSearch: "PyTorch MPS Apple Silicon performance optimization 2025" — General optimization patterns, anecdotal batch size recommendations
- WebSearch: "Marker PDF Surya OCR performance optimization batch size MPS 2025" — Community reports on MPS performance, needs validation

---
*Research completed: 2026-02-03*
*Ready for roadmap: yes*
