# Phase 12: Device Configuration - Context

**Gathered:** 2026-02-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Enable explicit MPS/CUDA device selection with validation and fallback for GPU acceleration. Detection runs on CPU while recognition runs on GPU (MPS/CUDA) as a workaround for known MPS bugs. Automatic fallback to CPU when GPU fails.

</domain>

<decisions>
## Implementation Decisions

### Device Selection
- Auto-detect device at runtime (no user configuration required)
- Priority order: CUDA > MPS > CPU (use best available)
- Detection once at startup or first use (Claude's discretion on timing)

### Fallback Strategy
- Log fallbacks at WARNING level (user should know performance degraded)
- Include fallback info in result metadata (which pages used GPU vs CPU)
- On OOM: reduce batch size first, then fall back to CPU if still fails
- Configurable retry limit with sensible default
- Add `--strict-gpu` flag to disable CPU fallback (fail if GPU unavailable)

### Detection/Recognition Split
- Detection model runs on CPU (workaround for MPS bugs)
- Recognition model runs on GPU (MPS or CUDA)
- If recognition fails on GPU, redo BOTH detection and recognition on CPU (not partial reuse)
- If MPS unavailable but CUDA available, use CUDA for recognition
- If neither MPS nor CUDA available, full CPU mode

### Claude's Discretion
- Log verbosity and format for device info
- Validation timing (startup vs lazy)
- Validation depth (flag check vs tensor allocation test)
- Memory checks and thresholds
- Device persistence and caching strategy
- Thread safety approach for parallel processing
- Benchmark integration with device config
- Documentation of the split workaround
- Separate timing for detection vs recognition phases

</decisions>

<specifics>
## Specific Ideas

- The detection/recognition split is a temporary workaround for MPS bugs — design should allow re-enabling full GPU when PyTorch fixes the issues
- Should work in CI/containers where GPU unavailable (graceful CPU fallback)
- Result metadata should make it clear which device processed each page for debugging

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 12-device-configuration*
*Context gathered: 2026-02-04*
