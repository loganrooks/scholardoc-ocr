# Requirements: scholardoc-ocr

**Defined:** 2026-02-03
**Core Value:** Produce accurate OCR text from scanned academic PDFs with minimal manual intervention, using quality-gated fallback to avoid expensive neural OCR unless needed.

## v2.1 Requirements

Requirements for v2.1 Performance milestone — Surya optimization for Apple Silicon.

### Device Configuration

- [x] **DEV-01**: Pipeline explicitly selects MPS device on Apple Silicon
- [x] **DEV-02**: Device availability validated at startup with actionable error messages
- [x] **DEV-03**: Automatic fallback to CPU when MPS unavailable or fails
- [x] **DEV-04**: Per-model device selection (detection on CPU, recognition on MPS) to work around MPS bugs

### Batch Optimization

- [ ] **BATCH-01**: Batch size configuration passed to Surya converter (currently ignored)
- [ ] **BATCH-02**: Surya environment variables set for batch tuning (RECOGNITION_BATCH_SIZE, DETECTOR_BATCH_SIZE, etc.)
- [ ] **BATCH-03**: Hardware-aware batch size defaults based on available memory
- [ ] **BATCH-04**: Cross-file page batching aggregates flagged pages across all files into single Surya call
- [ ] **BATCH-05**: Adaptive batch sizing adjusts based on actual memory pressure

### Model Management

- [ ] **MODEL-01**: Model caching persists loaded models across MCP requests
- [ ] **MODEL-02**: TTL-based cache eviction prevents memory bloat
- [ ] **MODEL-03**: Memory cleanup between documents (torch.mps.empty_cache + gc.collect)
- [ ] **MODEL-04**: Warm model pool pre-loads models on MCP server startup
- [ ] **MODEL-05**: Memory profiling integration tracks VRAM usage during processing

### Benchmarking & Metrics

- [x] **BENCH-01**: Baseline performance measurement infrastructure with pytest-benchmark
- [x] **BENCH-02**: Correct timing methodology using torch.mps.synchronize()
- [x] **BENCH-03**: Regression detection integrated into CI pipeline
- [x] **BENCH-04**: Memory profiling with memray for leak detection
- [x] **BENCH-05**: Hardware-specific benchmark profiles for M1/M2/M3 variants
- [x] **BENCH-06**: Surya processing time captured in phase_timings (model load + inference)
- [x] **BENCH-07**: Top-level engine field reflects actual processing (mixed/tesseract/surya)
- [x] **BENCH-08**: Quality scores re-evaluated after Surya processing

## v2.2 Requirements

Deferred bugs/improvements discovered during v2.1 planning. Not blocking performance work.

### MCP Usability

- **MCP-01**: `output_name` parameter actually renames output file
- **MCP-02**: JSON metadata file produced consistently on every run
- **MCP-03**: Investigate/document why Tesseract runs with `force_surya=true`

## v3.0 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Quality

- **QUAL-01**: Dictionary-based spell correction
- **QUAL-02**: N-gram perplexity scoring
- **QUAL-03**: Per-region quality scoring
- **QUAL-04**: Layout consistency checks

### Configuration

- **CONFIG-01**: Config file support (.scholardoc-ocr.yaml)
- **CONFIG-02**: Configurable domain dictionaries

### Preprocessing

- **PREPROC-01**: Image preprocessing with cv2 (deskew, denoise)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Multi-GPU support | Single Apple Silicon GPU is target use case |
| CUDA optimization | Apple Silicon only for v2.1 |
| Distributed processing | Single-machine tool for individual scholars |
| MLX migration | PyTorch MPS sufficient, MLX would be major rewrite |
| torch.compile optimization | MPS support is experimental, not stable enough |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DEV-01 | Phase 12 | Complete |
| DEV-02 | Phase 12 | Complete |
| DEV-03 | Phase 12 | Complete |
| DEV-04 | Phase 12 | Complete |
| BATCH-01 | Phase 14 | Pending |
| BATCH-02 | Phase 14 | Pending |
| BATCH-03 | Phase 14 | Pending |
| BATCH-04 | Phase 14 | Pending |
| BATCH-05 | Phase 14 | Pending |
| MODEL-01 | Phase 13 | Pending |
| MODEL-02 | Phase 13 | Pending |
| MODEL-03 | Phase 13 | Pending |
| MODEL-04 | Phase 13 | Pending |
| MODEL-05 | Phase 13 | Pending |
| BENCH-01 | Phase 11 | Complete |
| BENCH-02 | Phase 11 | Complete |
| BENCH-03 | Phase 11 | Complete |
| BENCH-04 | Phase 11 | Complete |
| BENCH-05 | Phase 11 | Complete |
| BENCH-06 | Phase 11 | Complete |
| BENCH-07 | Phase 11 | Complete |
| BENCH-08 | Phase 11 | Complete |

**Coverage:**
- v2.1 requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0

---
*Requirements defined: 2026-02-03*
*Last updated: 2026-02-03 after roadmap creation*
