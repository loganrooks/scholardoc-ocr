# Phase 5: CLI Presentation Layer - Research

**Researched:** 2026-01-30
**Domain:** Python CLI with Rich progress display wrapping a library API
**Confidence:** HIGH

## Summary

This phase rewrites `cli.py` as a thin presentation wrapper around the existing `run_pipeline()` library API. The current CLI already calls `run_pipeline()` and prints a summary, so the structural change is modest. The main work is: (1) implementing a `RichCallback` that implements `PipelineCallback` to drive Rich progress bars and spinners, (2) adding new flags (`--output-dir`, `--language`, `-r`), (3) fixing the recursive mode bug, and (4) ensuring the CLI never imports backend modules directly.

The callback protocol (`PipelineCallback`) already exists with `on_progress`, `on_phase`, and `on_model` methods — and `run_pipeline()` already accepts an optional `callback` parameter. This means the Rich integration is purely a matter of writing a new callback class.

**Primary recommendation:** Create a `RichCallback(PipelineCallback)` class in cli.py (or a small `_display.py` helper) that translates pipeline events into Rich progress bar updates and spinner state. The CLI module imports only `PipelineConfig`, `run_pipeline`, `BatchResult`, and callback types from the library.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| rich | >=13.0.0 | Progress bars, spinners, colored output, tables | Already a dependency in pyproject.toml |
| argparse | stdlib | CLI argument parsing | Already in use, no reason to change |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich.progress.Progress | (part of rich) | Multi-task progress bars with custom columns | Tesseract phase (per-file) and Surya phase (per-file) |
| rich.console.Console | (part of rich) | Colored output, status spinners, tables | Summary output, "Loading Surya models..." spinner |
| rich.table.Table | (part of rich) | Formatted summary table | Final results display |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| argparse | click/typer | More features but unnecessary dependency; current argparse works fine |
| Rich tables for summary | Plain print (current) | Rich tables look better; Rich is already a dep |

**Installation:** Already installed — `rich>=13.0.0` is in pyproject.toml dependencies.

## Architecture Patterns

### Recommended Structure
```
src/scholardoc_ocr/
├── cli.py              # Thin wrapper: argparse + RichCallback + summary printing
├── pipeline.py         # run_pipeline() — CLI imports only this + types
├── callbacks.py        # PipelineCallback protocol + LoggingCallback + NullCallback
├── types.py            # BatchResult, FileResult, etc.
└── (other backend modules CLI must NOT import)
```

### Pattern 1: Rich Callback implementing PipelineCallback
**What:** A class in cli.py that implements the existing `PipelineCallback` protocol using Rich's `Progress` and `Console` objects.
**When to use:** Always — this is the core pattern for this phase.
**Example:**
```python
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn

class RichCallback:
    """PipelineCallback implementation using Rich for terminal display."""

    def __init__(self, console: Console) -> None:
        self.console = console
        self._progress: Progress | None = None
        self._task_id = None

    def on_phase(self, event: PhaseEvent) -> None:
        if event.status == "started":
            self._progress = Progress(
                SpinnerColumn(),
                TextColumn("[bold blue]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=self.console,
            )
            self._progress.start()
            desc = f"Phase: {event.phase} ({event.files_count} files)"
            self._task_id = self._progress.add_task(desc, total=event.files_count)
        elif event.status == "completed" and self._progress:
            self._progress.stop()
            self._progress = None

    def on_progress(self, event: ProgressEvent) -> None:
        if self._progress and self._task_id is not None:
            self._progress.update(
                self._task_id,
                completed=event.current,
                description=f"{event.phase}: {event.filename or ''}",
            )

    def on_model(self, event: ModelEvent) -> None:
        if event.status == "loading":
            self.console.print(f"[yellow]Loading {event.model_name} models...[/]")
        elif event.status == "loaded":
            self.console.print(
                f"[green]{event.model_name} models loaded ({event.time_seconds:.1f}s)[/]"
            )
```

### Pattern 2: Console.status() for model loading spinner
**What:** Use `console.status()` context manager for the "Loading Surya models..." spinner.
**When to use:** The `on_model` callback with status="loading" triggers a spinner; status="loaded" stops it.
**Note:** Since the callback is event-driven (not context-manager-driven), use `Console.status()` started/stopped manually, or simply print a message with a spinner column in the progress bar.

### Pattern 3: Summary as Rich Table
**What:** Replace the current plain-text `_print_summary()` with a `rich.table.Table`.
**Example:**
```python
from rich.table import Table

table = Table(title="OCR Pipeline Summary")
table.add_column("Filename", style="cyan")
table.add_column("Pages", justify="right")
table.add_column("Quality", justify="right")
table.add_column("Engine")
table.add_column("Time", justify="right")
for f in batch.files:
    if f.success:
        quality_style = "green" if f.quality_score >= 0.85 else "yellow"
        table.add_row(f.filename, str(f.page_count),
                       f"{f.quality_score:.1%}", str(f.engine),
                       f"{f.time_seconds:.1f}s")
console.print(table)
```

### Anti-Patterns to Avoid
- **Importing processor/quality/surya in cli.py:** CLI must only import pipeline, callbacks, and types
- **Putting business logic in the callback:** The callback should only translate events to display; no decisions
- **Blocking on Rich inside callback methods called from worker processes:** The callback runs in the main process (pipeline dispatches events from main thread after futures complete), so this is safe — but do NOT try to pass Rich objects across process boundaries

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Progress bars | Custom print-based progress | `rich.progress.Progress` | Handles terminal width, refresh rate, ETA calculation |
| Colored output | ANSI escape codes | `rich.console.Console` | Handles NO_COLOR, terminal detection |
| Tables | Format strings with padding | `rich.table.Table` | Auto-column-width, borders, styles |
| Spinner | Custom animation loop | `Console.status()` | Handles animation threading |
| NO_COLOR support | Manual env var check | Rich auto-detects `NO_COLOR` env var and `--no-color` via `Console(no_color=...)` | Standard protocol |

## Common Pitfalls

### Pitfall 1: Recursive mode file path bug
**What goes wrong:** `rglob("*.pdf")` returns full paths but `p.name` strips the subdirectory, so `config.input_dir / filename` can't find files in subdirectories.
**Why it happens:** Line 171 of current cli.py: `pdf_files = [p.name for p in input_dir.rglob("*.pdf")]`
**How to avoid:** Store relative paths from input_dir: `pdf_files = [str(p.relative_to(input_dir)) for p in input_dir.rglob("*.pdf")]`. The pipeline's file discovery (`config.input_dir / filename`) then resolves correctly.
**Warning signs:** Files in subdirectories silently not found during Surya phase.

### Pitfall 2: Rich Progress and logging conflict
**What goes wrong:** Python `logging` output interleaves with Rich progress bars, corrupting the display.
**Why it happens:** Both write to stderr/stdout simultaneously.
**How to avoid:** Use `rich.logging.RichHandler` as the logging handler, or redirect logging through the Rich console. Alternatively, suppress logging output during progress display.

### Pitfall 3: Console.status() not composable with Progress
**What goes wrong:** You can't have a `console.status()` spinner AND a `Progress()` bar active simultaneously on the same console.
**Why it happens:** Both use Live display internally and only one Live can be active.
**How to avoid:** For the Surya model loading, either (a) show the spinner BEFORE starting the progress bar, or (b) use a progress task with a spinner column instead of a separate status. Since `on_model(loading)` fires before `on_progress` for surya, option (a) works naturally.

### Pitfall 4: CLI importing backend modules
**What goes wrong:** Violates the "thin wrapper" design, making CLI and library coupled.
**Why it happens:** Temptation to import processor or quality for direct access.
**How to avoid:** Enforce that cli.py only imports from: `pipeline` (PipelineConfig, run_pipeline), `callbacks` (PipelineCallback, event types), `types` (BatchResult, FileResult, OCREngine). Nothing else.

### Pitfall 5: Language flag mapping complexity
**What goes wrong:** User passes `--language en,fr` but Tesseract needs `eng,fra` and Surya needs `en,fr`.
**Why it happens:** Different OCR engines use different language codes.
**How to avoid:** Accept a simple format (ISO 639-1 two-letter codes like `en,fr,el,la`) and map internally. The mapping table is small and static. Put the mapping in cli.py or a shared constants module.

## Code Examples

### Current callback protocol (already exists)
```python
# From callbacks.py — this is the interface to implement
@runtime_checkable
class PipelineCallback(Protocol):
    def on_progress(self, event: ProgressEvent) -> None: ...
    def on_phase(self, event: PhaseEvent) -> None: ...
    def on_model(self, event: ModelEvent) -> None: ...
```

### Current pipeline invocation (already exists)
```python
# From pipeline.py — already accepts callback
def run_pipeline(config: PipelineConfig, callback: PipelineCallback | None = None) -> BatchResult:
```

### Rich Progress with custom columns
```python
# Source: Context7 /textualize/rich
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn,
    TaskProgressColumn, TimeRemainingColumn,
)

with Progress(
    SpinnerColumn(),
    TextColumn("[bold blue]{task.description}"),
    BarColumn(),
    TaskProgressColumn(),
    TimeRemainingColumn(),
) as progress:
    task = progress.add_task("[cyan]Processing...", total=100)
    progress.update(task, advance=1)
```

### Rich Console with NO_COLOR support
```python
import os
from rich.console import Console

# Rich respects NO_COLOR env var automatically
console = Console(no_color=os.environ.get("NO_COLOR") is not None)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| print() summary | Rich tables + progress | This phase | Better UX |
| No progress feedback | Rich Progress callback | This phase | Users see what's happening |
| Logging-only progress | Rich live display | This phase | Visual progress bars |

## Open Questions

1. **PipelineConfig needs language fields**
   - What we know: PipelineConfig currently hardcodes languages in `config_dict` inside `run_pipeline()`
   - What's unclear: Whether to add language fields to PipelineConfig or pass them differently
   - Recommendation: Add `langs_tesseract` and `langs_surya` fields to PipelineConfig; CLI maps from `--language` flag

2. **Output dir flag vs existing behavior**
   - What we know: Current CLI has `-o`/`--output` flag that sets output_dir. The context says add `--output-dir`/`-o`.
   - What's unclear: Whether to rename `--output` to `--output-dir` (breaking) or alias
   - Recommendation: Keep `-o` short flag, rename long form to `--output-dir` for clarity. This is a minor breaking change on the long form only.

3. **Progress bar lifecycle management**
   - What we know: Callback methods are individual event handlers, not context managers
   - What's unclear: Best way to manage Progress start/stop lifecycle from event callbacks
   - Recommendation: Start Progress on `on_phase(started)`, stop on `on_phase(completed)`. Store as instance state.

## Sources

### Primary (HIGH confidence)
- Context7 `/textualize/rich` — Progress bars, spinners, console status, custom columns
- Codebase inspection — cli.py, pipeline.py, callbacks.py, types.py, pyproject.toml

### Secondary (MEDIUM confidence)
- Rich auto-detects NO_COLOR per https://no-color.org/ convention (verified via Context7 docs)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — Rich is already a dependency, argparse already in use
- Architecture: HIGH — PipelineCallback protocol and run_pipeline(callback=) already exist
- Pitfalls: HIGH — Recursive bug confirmed by code inspection; Rich composability verified via docs

**Research date:** 2026-01-30
**Valid until:** 2026-03-01 (stable domain, no fast-moving parts)
