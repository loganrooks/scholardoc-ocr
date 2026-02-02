# Phase 7: Fix MCP output_path Integration - Research

**Researched:** 2026-02-02
**Domain:** Python dataclass plumbing / MCP server post-processing
**Confidence:** HIGH

## Summary

The MCP server's `extract_text` and `output_name` features are broken because `FileResult` has no `output_path` field. The pipeline creates output PDFs at known paths (`output_dir/final/{stem}.pdf`) but never records those paths in `FileResult`. When the MCP server calls `result_dict.get("output_path", "")`, it gets an empty string, so both features silently fail.

The fix is straightforward: add `output_path` to `FileResult`, populate it in the pipeline worker, serialize it in `to_dict()`, and the MCP server code already handles the rest correctly.

**Primary recommendation:** Add `output_path: str | None = None` to `FileResult`, populate it in `_tesseract_worker` at each return point, and include it in `to_dict()`.

## Standard Stack

No new libraries needed. This is purely internal dataclass/plumbing work.

## Architecture Patterns

### The Gap

```
Pipeline (_tesseract_worker)          FileResult              MCP Server
─────────────────────────             ──────────              ──────────
Creates: final/{stem}.pdf  ──X──>    No output_path  ──X──>  get("output_path","") = ""
                                      field exists             extract_text fails silently
                                                               output_name fails silently
```

### The Fix

```
Pipeline (_tesseract_worker)          FileResult              MCP Server
─────────────────────────             ──────────              ──────────
Creates: final/{stem}.pdf  ────>     output_path set  ────>  get("output_path") works
                                                               extract_text writes .txt
                                                               output_name renames file
```

### Locations requiring changes

1. **`types.py` — `FileResult` dataclass** (line ~103): Add `output_path: str | None = None`
2. **`types.py` — `FileResult.to_dict()`** (line ~126): Include `output_path` in dict
3. **`pipeline.py` — `_tesseract_worker`** (3 return points):
   - Line ~108 (existing text good enough): set `output_path = str(pdf_path)`
   - Line ~130 (Tesseract failed): `output_path` stays None
   - Line ~176 (Tesseract succeeded): set `output_path = str(pdf_path)`

### Return points in _tesseract_worker

| Line | Condition | pdf_path available? | Action |
|------|-----------|---------------------|--------|
| ~108 | Existing text good | Yes (`final/{stem}.pdf`) | Set output_path |
| ~130 | Tesseract failed | No | Leave None |
| ~176 | Tesseract done | Yes (`final/{stem}.pdf`) | Set output_path |

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Path tracking | Custom path registry | Single field on FileResult | Simplest possible fix |

## Common Pitfalls

### Pitfall 1: Forgetting a return point
**What goes wrong:** One of the 3 return paths in `_tesseract_worker` doesn't set `output_path`
**How to avoid:** Audit all 3 return statements; add test coverage for each path

### Pitfall 2: Surya phase also creates output but doesn't update output_path
**What goes wrong:** After Surya enhancement, the output PDF path is the same (Surya modifies text, not the PDF itself in current code), so this is actually fine. But verify.
**How to avoid:** Check that Surya phase doesn't change the PDF output location

### Pitfall 3: Path serialization
**What goes wrong:** `Path` objects aren't JSON-serializable
**How to avoid:** Store as `str` in FileResult, or convert in `to_dict()`

## Code Examples

### Adding output_path to FileResult
```python
@dataclass
class FileResult:
    filename: str
    success: bool
    engine: OCREngine
    quality_score: float
    page_count: int
    pages: list[PageResult]
    error: str | None = None
    output_path: str | None = None  # <-- NEW
    time_seconds: float = 0.0
    phase_timings: dict[str, float] = field(default_factory=dict)

    def to_dict(self, include_text: bool = False) -> dict:
        d: dict = {
            "filename": self.filename,
            "success": self.success,
            "engine": str(self.engine),
            "quality_score": self.quality_score,
            "page_count": self.page_count,
            "pages": [p.to_dict(include_text=include_text) for p in self.pages],
            "time_seconds": self.time_seconds,
            "phase_timings": self.phase_timings,
        }
        if self.output_path is not None:
            d["output_path"] = self.output_path
        if self.error is not None:
            d["error"] = self.error
        return d
```

### Populating in _tesseract_worker (existing-text-good path)
```python
return FileResult(
    filename=input_path.name,
    success=True,
    engine=OCREngine.EXISTING,
    quality_score=overall_quality,
    page_count=page_count,
    pages=pages,
    output_path=str(pdf_path),  # <-- NEW
    time_seconds=time.time() - start,
    phase_timings=timings,
)
```

## State of the Art

N/A — this is an internal bug fix, not a technology choice.

## Open Questions

1. **Should output_path always be present in to_dict()?**
   - Current approach: only include when not None (matches error field pattern)
   - Alternative: always include, use empty string for failures
   - Recommendation: Only when not None, consistent with existing pattern

## Sources

### Primary (HIGH confidence)
- Direct code reading of `types.py`, `pipeline.py`, `mcp_server.py` in the repository

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies
- Architecture: HIGH - direct code reading, clear gap identified
- Pitfalls: HIGH - straightforward change with known return points

**Research date:** 2026-02-02
**Valid until:** N/A (internal bug fix, not version-dependent)
