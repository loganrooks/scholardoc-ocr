# Phase 4: Engine Orchestration - Context

**Gathered:** 2026-01-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix pipeline orchestration to use per-file Surya batching with shared models, eliminate cross-file index mapping, write Surya results back to output files, and implement resource-aware parallelism. Separates library orchestration from CLI presentation.

</domain>

<decisions>
## Implementation Decisions

### Failure & recovery behavior
- Partial success per file: if Surya succeeds on some pages but fails on others, write what worked — successful pages get Surya text, failed pages keep Tesseract text
- Track before/after quality scores per page (pre-Surya and post-Surya) for threshold tuning
- Separate `--force-surya` flag to explicitly run Surya regardless of quality (distinct from `--force` which means re-process)

### Pipeline result reporting
- Full page breakdown per file: per-page quality scores (before/after Surya), which engine produced each page, error details
- Include timing information per file: Tesseract duration, quality analysis duration, Surya duration (if run)
- Pipeline-level summary: total files, total pages, pages improved by Surya, overall success rate

### Claude's Discretion
- **Failure handling**: whether to keep Tesseract output or mark file as failed on Surya error; retry policy for Surya failures; pipeline-level exception vs. always-return-results behavior; error logging approach
- **Parallelism**: sequential vs. overlapping phases; worker count auto-detection; thread nesting coordination with ocrmypdf; memory checks before Surya model loading; CPU-only vs. CPU+RAM aware worker limits; graceful cancellation; incremental skip of already-processed files; progress callback granularity (file vs. page level)
- **Surya batching**: per-file sequential processing (aligns with eliminating cross-file index mapping); minimum page threshold to trigger Surya; sub-batching for large files; post-Surya quality re-check; writeback strategy (per-page replacement vs. full file rewrite)
- **Surya-only mode**: whether to support skipping Tesseract entirely
- **Result serialization**: JSON-serializable results or dataclasses-only

</decisions>

<specifics>
## Specific Ideas

- User wants before/after quality scores tracked per page — important for tuning the quality threshold
- Separate `--force-surya` flag was specifically requested (not overloading `--force`)
- Full page breakdown with engine attribution (which engine produced each page) was specifically requested
- Timing data per file was specifically requested for performance tuning

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-engine-orchestration*
*Context gathered: 2026-01-29*
