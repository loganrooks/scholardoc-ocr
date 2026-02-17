# Stack Research: Diagnostic Intelligence & Evaluation Tooling

**Domain:** OCR diagnostic instrumentation, LLM-based evaluation, image quality analysis
**Researched:** 2026-02-17
**Confidence:** HIGH

## Executive Summary

The v3.0 milestone requires surprisingly few new dependencies. The existing transitive dependency tree -- inherited from marker-pdf, surya-ocr, and ocrmypdf -- already provides Pillow (10.4.0), numpy (2.4.2), scipy (1.17.0), opencv-python-headless (4.11.0.86), and pydantic (2.12.5). These cover image quality analysis, statistical correlation, computer vision operations, and structured schema validation respectively.

The only genuinely new production dependency is **none at all**. Everything needed for image quality metrics (DPI, contrast, noise, skew) is already available through Pillow + numpy + opencv-python-headless. LLM evaluation uses subprocess to invoke `claude` and `codex` CLIs directly -- no SDK package needed since the user explicitly requires account-based CLI invocation, not API keys. Text diffing uses Python's stdlib `difflib`. Structured evaluation output uses pydantic (already transitive) for JSON schema generation and validation.

**Key insight:** The project's existing dependency tree is remarkably well-suited for this milestone. The risk is accidentally adding redundant packages that duplicate what transitive deps already provide.

## Current Transitive Dependencies (Already Installed)

These packages are installed via marker-pdf, surya-ocr, ocrmypdf, or their sub-dependencies. They are NOT listed in scholardoc-ocr's direct `dependencies` in pyproject.toml, but they are guaranteed to be present at runtime.

| Package | Installed Version | Pulled By | v3.0 Use |
|---------|-------------------|-----------|----------|
| Pillow | 10.4.0 | marker-pdf, ocrmypdf, surya-ocr, pytesseract | Image quality metrics: histogram stats, contrast, DPI extraction |
| numpy | 2.4.2 | opencv-python-headless, scipy, scikit-learn | Array ops for image analysis, statistical computations |
| scipy | 1.17.0 | scikit-learn (via marker-pdf) | Pearson/Spearman correlation for quality score vs ground truth |
| opencv-python-headless | 4.11.0.86 | surya-ocr | Skew detection (Hough transform), noise estimation (Laplacian variance) |
| pydantic | 2.12.5 | marker-pdf, surya-ocr, mcp | Evaluation result schemas, JSON schema generation for LLM output |
| rapidfuzz | 3.14.3 | marker-pdf | Fast fuzzy string matching for OCR output vs ground truth comparison |

**Important:** These are transitive dependencies. If marker-pdf or surya-ocr were ever removed, these would disappear. For v3.0, this is fine -- the diagnostic tooling is inherently coupled to the OCR pipeline that brings these deps. If diagnostic features ever need to stand alone, promote the needed packages to direct dependencies at that point.

## Recommended Stack: Image Quality Analysis

### Core: Pillow + numpy (already available)

Image quality metrics require rendering PDF pages to images and computing statistics. The existing `confidence.py` already does this exact workflow:

```python
# From confidence.py -- this pattern already exists in the codebase
with fitz.open(pdf_path) as doc:
    page = doc[page_num]
    pix = page.get_pixmap(dpi=300)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
```

**DPI Detection:** PyMuPDF's `page.get_pixmap(dpi=N)` renders at controlled DPI. For embedded image DPI, use `doc.extract_image(xref)` which returns `xres` and `yres` fields. No new dependency needed.

**Contrast Analysis:** Pillow's `ImageStat.Stat(img)` provides per-channel mean, stddev, min, max, median from the histogram. Standard deviation of luminance is a direct contrast proxy. This is exactly what `PIL.ImageStat` is designed for.

```python
from PIL import ImageStat, ImageOps
import numpy as np

def compute_contrast(img: Image.Image) -> float:
    """Compute RMS contrast from grayscale image."""
    gray = ImageOps.grayscale(img)
    stat = ImageStat.Stat(gray)
    return stat.stddev[0] / 255.0  # Normalized 0-1
```

**Noise Estimation:** The Laplacian variance method is the standard approach for estimating image noise/blur in document images. Uses opencv-python-headless (already transitive):

```python
import cv2
import numpy as np

def estimate_noise(img_array: np.ndarray) -> float:
    """Laplacian variance -- higher = sharper/noisier, lower = blurry."""
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()
```

**Skew Detection:** Hough transform via opencv-python-headless. ~20 lines of code, no need for the `deskew` library (which would pull in scikit-image, an unnecessary new dependency):

```python
import cv2
import numpy as np

def detect_skew_angle(img_array: np.ndarray) -> float:
    """Detect document skew angle using Hough transform. Returns degrees."""
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100, minLineLength=100, maxLineGap=10)
    if lines is None:
        return 0.0
    angles = [np.degrees(np.arctan2(y2 - y1, x2 - x1)) for [[x1, y1, x2, y2]] in lines]
    # Filter to near-horizontal lines (document text lines)
    horiz = [a for a in angles if abs(a) < 45]
    return float(np.median(horiz)) if horiz else 0.0
```

### What NOT to Use for Image Quality

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `deskew` (PyPI) | Pulls in `scikit-image` -- large new dependency for something achievable with existing opencv | OpenCV Hough transform (already installed) |
| `scikit-image` | ~80MB install, overlaps heavily with existing opencv-python-headless and Pillow | Pillow + numpy + opencv for everything needed |
| `wand` / ImageMagick | External C dependency, system-level install complexity | PyMuPDF for PDF rendering, Pillow for image manipulation |
| `rawpy` / `imageio` | Unnecessary abstraction layers | Direct numpy arrays from PyMuPDF pixmaps |

## Recommended Stack: LLM CLI Invocation

### Core: Python `subprocess` (stdlib)

The user requires account-based CLI invocation of `claude` and `codex` commands, not API SDK usage. Both CLIs support non-interactive JSON output.

**Claude Code CLI** (installed via `npm install -g @anthropic-ai/claude-code`):

```python
import subprocess
import json

def evaluate_with_claude(
    prompt: str,
    system_prompt: str | None = None,
    json_schema: dict | None = None,
    model: str = "sonnet",
    max_turns: int = 1,
) -> dict:
    """Invoke claude CLI in print mode with structured JSON output."""
    cmd = ["claude", "-p", "--output-format", "json", "--model", model, "--max-turns", str(max_turns)]
    if system_prompt:
        cmd.extend(["--system-prompt", system_prompt])
    if json_schema:
        cmd.extend(["--json-schema", json.dumps(json_schema)])
    cmd.append(prompt)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    return json.loads(result.stdout)
```

Key Claude CLI flags for evaluation:
- `--print` / `-p`: Non-interactive mode, prints response and exits
- `--output-format json`: Structured JSON output for programmatic parsing
- `--json-schema '{...}'`: Validates output against a JSON Schema (post-workflow)
- `--model sonnet`: Model selection (sonnet for speed, opus for quality)
- `--max-turns 1`: Single-turn evaluation (no tool use needed)
- `--system-prompt "..."`: Custom evaluation instructions
- `--max-budget-usd 5.00`: Cost cap for evaluation runs

**Codex CLI** (installed via `npm install -g @openai/codex`):

```python
def evaluate_with_codex(
    prompt: str,
    output_schema_path: str | None = None,
    model: str | None = None,
) -> dict:
    """Invoke codex CLI in exec mode with structured output."""
    cmd = ["codex", "exec", "--json"]
    if output_schema_path:
        cmd.extend(["--output-schema", output_schema_path])
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    # codex --json outputs JSONL events; parse the final turn.completed event
    events = [json.loads(line) for line in result.stdout.strip().splitlines() if line.strip()]
    return events
```

Key Codex CLI flags for evaluation:
- `codex exec`: Non-interactive execution mode
- `--json`: JSONL event stream output
- `--output-schema path.json`: Validate final response against JSON Schema
- `--model`: Model override
- `--ephemeral`: No session persistence (clean evaluation)

### Why NOT Use SDK Packages

| Package | Why Skip |
|---------|----------|
| `claude-agent-sdk` (v0.1.37) | Bundles its own Claude Code CLI binary (~100MB). The user already has claude CLI installed account-based. Using subprocess avoids dependency on Anthropic's bundled binary versioning and keeps the eval tooling lightweight. |
| `openai-codex-sdk` (v0.1.11) | Community-maintained, not official. The official Codex SDK is TypeScript-only. Raw subprocess is more reliable and transparent. |
| `claude-code-sdk` (v0.0.25) | Deprecated. Replaced by claude-agent-sdk. |
| `anthropic` Python SDK | Requires API key. User wants account-based CLI invocation. |
| `openai` Python SDK | Requires API key. User wants codex CLI account-based invocation. |

**Philosophy:** For evaluation tooling that invokes external CLIs, thin subprocess wrappers in your own code are superior to SDK packages. You control the interface, avoid version coupling, and the CLIs' `--json` / `--output-format json` flags already provide structured output.

## Recommended Stack: Structured Evaluation Output

### Core: pydantic (already transitive) + stdlib json

Pydantic (v2.12.5, already installed via marker-pdf and surya-ocr) provides:
- Dataclass-like models with automatic JSON Schema generation
- Runtime validation of evaluation results
- `model_json_schema()` to generate JSON Schema for `--json-schema` (claude) and `--output-schema` (codex)

```python
from pydantic import BaseModel, Field

class EvaluationResult(BaseModel):
    """Schema for LLM evaluation of OCR output quality."""
    page_number: int
    overall_quality: float = Field(ge=0, le=1, description="Overall quality 0-1")
    readability: float = Field(ge=0, le=1)
    accuracy_estimate: float = Field(ge=0, le=1)
    issues: list[str] = Field(default_factory=list)
    reasoning: str = Field(description="Why this quality score was assigned")

# Generate JSON Schema for CLI --json-schema flag
schema = EvaluationResult.model_json_schema()
```

**Why pydantic over plain dataclasses:** The project already uses dataclasses extensively (types.py, quality.py). For evaluation schemas that need JSON Schema generation, runtime validation, and serialization, pydantic is the right tool -- and it costs nothing since it is already installed. Use dataclasses for internal types, pydantic for external evaluation schemas.

### Why NOT Add These

| Avoid | Reason |
|-------|--------|
| `jsonschema` package | Pydantic already validates against schemas. Adding jsonschema is redundant. |
| `attrs` | Different paradigm from existing codebase (dataclasses). Pydantic covers the validation need. |
| `marshmallow` | Serialization library that overlaps with pydantic. Not needed. |

## Recommended Stack: Text Diff/Comparison

### Core: stdlib `difflib` + transitive `rapidfuzz`

**difflib (stdlib):** For structured Tesseract-vs-Surya output comparison:
- `SequenceMatcher.ratio()`: Overall similarity score (0-1)
- `SequenceMatcher.get_opcodes()`: Structured edit operations (equal/insert/delete/replace)
- `unified_diff()`: Human-readable diff output for reports
- `HtmlDiff`: Side-by-side HTML comparison for visual inspection

**rapidfuzz (v3.14.3, already transitive via marker-pdf):** For fuzzy token-level matching between OCR output and ground truth. Significantly faster than difflib for large texts (C++ backend).

```python
from difflib import SequenceMatcher, unified_diff
from rapidfuzz import fuzz, process

def compare_ocr_outputs(tesseract_text: str, surya_text: str) -> dict:
    """Compare Tesseract vs Surya output with structured diff."""
    sm = SequenceMatcher(None, tesseract_text, surya_text)
    opcodes = sm.get_opcodes()
    return {
        "similarity": sm.ratio(),
        "operations": [
            {"tag": tag, "i1": i1, "i2": i2, "j1": j1, "j2": j2}
            for tag, i1, i2, j1, j2 in opcodes
            if tag != "equal"
        ],
        "diff_lines": list(unified_diff(
            tesseract_text.splitlines(),
            surya_text.splitlines(),
            fromfile="tesseract",
            tofile="surya",
        )),
    }

def score_against_ground_truth(ocr_text: str, ground_truth: str) -> float:
    """Fuzzy match score using rapidfuzz (faster than difflib for large texts)."""
    return fuzz.ratio(ocr_text, ground_truth) / 100.0
```

## Recommended Stack: Statistical Analysis

### Core: scipy.stats + numpy (both already transitive)

For correlating quality scores against ground truth and analyzing quality metric distributions:

```python
from scipy import stats
import numpy as np

def analyze_quality_correlation(
    quality_scores: list[float],
    ground_truth_scores: list[float],
) -> dict:
    """Correlate automated quality scores with ground truth evaluations."""
    r_pearson, p_pearson = stats.pearsonr(quality_scores, ground_truth_scores)
    r_spearman, p_spearman = stats.spearmanr(quality_scores, ground_truth_scores)
    return {
        "pearson_r": r_pearson,
        "pearson_p": p_pearson,
        "spearman_r": r_spearman,
        "spearman_p": p_spearman,
        "n": len(quality_scores),
        "quality_mean": float(np.mean(quality_scores)),
        "quality_std": float(np.std(quality_scores)),
    }
```

## Recommended Stack: Image Extraction from PDF

### Core: PyMuPDF (already a direct dependency)

PyMuPDF handles all PDF-to-image needs. The codebase already renders pages to images in `confidence.py`. For evaluation, extend this pattern:

```python
import fitz
import io
from PIL import Image

def extract_page_image(pdf_path: Path, page_num: int, dpi: int = 300) -> Image.Image:
    """Extract a page as a PIL Image for evaluation."""
    with fitz.open(pdf_path) as doc:
        page = doc[page_num]
        pix = page.get_pixmap(dpi=dpi)
        return Image.open(io.BytesIO(pix.tobytes("png")))

def extract_embedded_image_dpi(pdf_path: Path, page_num: int) -> list[dict]:
    """Get DPI of images embedded in a PDF page."""
    with fitz.open(pdf_path) as doc:
        page = doc[page_num]
        images = page.get_images(full=True)
        results = []
        for img_info in images:
            xref = img_info[0]
            img_data = doc.extract_image(xref)
            results.append({
                "xref": xref,
                "xres": img_data.get("xres", 0),
                "yres": img_data.get("yres", 0),
                "width": img_data.get("width", 0),
                "height": img_data.get("height", 0),
                "colorspace": img_data.get("cs-name", "unknown"),
            })
        return results
```

## Summary: Changes to pyproject.toml

### Production Dependencies: NO CHANGES

```toml
# pyproject.toml -- dependencies section stays EXACTLY as-is
dependencies = [
    "cachetools>=5.0.0",
    "marker-pdf>=1.0.0",
    "ocrmypdf>=16.0.0",
    "psutil>=5.9.0",
    "pymupdf>=1.24.0",
    "pytesseract>=0.3.10",
    "rich>=13.0.0",
]
```

**Rationale:** Every library needed for v3.0 diagnostic features is either:
1. Already a direct dependency (PyMuPDF, Rich)
2. Already a transitive dependency (Pillow, numpy, scipy, opencv-python-headless, pydantic, rapidfuzz)
3. Part of Python's standard library (subprocess, difflib, json, statistics, dataclasses)

### Optional Dependencies: Add `eval` extra

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.4.0",
    "pytest-benchmark>=5.0",
    "pytest-memray>=1.0",
    "memray>=1.0",
]
mcp = ["mcp[cli]"]
eval = [
    # Pin transitive deps as direct for evaluation stability
    # These are already installed via marker-pdf/surya-ocr, but pinning
    # ensures they remain available even if upstream changes
    "pydantic>=2.7.0",
]
```

**Why pin pydantic in eval extra:** Pydantic is the only transitive dependency that the evaluation framework will use as a primary interface (schema generation, validation). If marker-pdf ever dropped its pydantic dependency, the eval tooling would break. Pinning it in an optional `[eval]` extra makes the dependency explicit without bloating the default install. Pillow, numpy, scipy, and opencv are so deeply embedded in the OCR stack that they will never disappear as transitives.

### System Requirements (not pip-installable)

```bash
# Claude Code CLI (for LLM evaluation)
npm install -g @anthropic-ai/claude-code
# Verify: claude --version

# Codex CLI (for LLM evaluation)
npm install -g @openai/codex
# Verify: codex --version
```

## Integration Points with Existing Stack

| Existing Module | v3.0 Integration | How |
|-----------------|------------------|-----|
| `processor.py` (PyMuPDF) | Image extraction for quality analysis | Extend with `extract_page_image()`, `extract_embedded_image_dpi()` |
| `confidence.py` (Pillow + fitz) | Already renders pages to images | Reuse the `fitz.open() -> get_pixmap() -> PIL.Image` pattern |
| `quality.py` (QualityAnalyzer) | Add image quality signal alongside text signals | New `ImageQualitySignal` class returning `SignalResult` |
| `types.py` (dataclasses) | Evaluation result types | New pydantic models for evaluation schemas, existing dataclasses for internal types |
| `cli.py` (Rich) | Evaluation report display | Rich tables for eval results, same pattern as `_print_summary()` |
| `batch.py` | Batch evaluation across files | Collect evaluation results per-page, aggregate stats |

## Version Compatibility Matrix

| Package | Min Version (pinned) | Installed | Compatible With |
|---------|---------------------|-----------|-----------------|
| PyMuPDF | >=1.24.0 | 1.24.x+ | Python 3.11-3.13, Pillow 10.x |
| Pillow | >=10.1.0 (via marker-pdf) | 10.4.0 | Python 3.11-3.13, numpy 2.x |
| numpy | >=1.26.4 (via scipy) | 2.4.2 | Python 3.11-3.13 |
| scipy | >=1.10.0 (via scikit-learn) | 1.17.0 | numpy 2.4.x |
| opencv-python-headless | ==4.11.0.86 (via surya) | 4.11.0.86 | numpy 2.x, Python 3.11-3.13 |
| pydantic | >=2.4.2 (via marker-pdf) | 2.12.5 | Python 3.11-3.13 |
| rapidfuzz | >=3.8.1 (via marker-pdf) | 3.14.3 | Python 3.11-3.13 |

**Note:** Pillow is pinned at `<11.0.0` by marker-pdf. If Pillow 11 introduces breaking changes, marker-pdf will need to update first. This is marker-pdf's problem, not ours.

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| Image stats | Pillow ImageStat + numpy | scikit-image | scikit-image is ~80MB, not installed, overlaps with existing Pillow + opencv |
| Skew detection | OpenCV Hough transform | `deskew` package | deskew pulls in scikit-image; we already have opencv |
| Fuzzy matching | rapidfuzz (transitive) | `fuzzywuzzy` | fuzzywuzzy is slower (pure Python), rapidfuzz is already installed |
| JSON schemas | pydantic (transitive) | `jsonschema` + dataclasses | pydantic generates AND validates schemas; jsonschema only validates |
| LLM invocation | subprocess + CLIs | claude-agent-sdk / openai SDK | User requires account-based CLI, not API key-based SDK |
| Text diff | difflib (stdlib) | `deepdiff` | difflib is stdlib, zero-cost, sufficient for text comparison |
| Statistics | scipy.stats (transitive) | `pingouin` or `statsmodels` | scipy already installed, provides pearson/spearman which is all we need |
| Image rendering | PyMuPDF (direct dep) | `pdf2image` (poppler wrapper) | PyMuPDF already does this, no system dependency needed |

## Sources

- [Pillow ImageStat Documentation](https://pillow.readthedocs.io/en/stable/reference/ImageStat.html) -- Histogram-based image statistics (v12.1.1 docs, features stable since v10.x)
- [PyMuPDF Pixmap Documentation](https://pymupdf.readthedocs.io/en/latest/pixmap.html) -- DPI control, image extraction, format conversion
- [PyMuPDF Images Recipe](https://pymupdf.readthedocs.io/en/latest/recipes-images.html) -- Extract embedded images with DPI metadata
- [Claude Code CLI Reference](https://code.claude.com/docs/en/cli-reference) -- `--print`, `--output-format json`, `--json-schema`, `--model`, `--max-turns`
- [Codex CLI Reference](https://developers.openai.com/codex/cli/reference/) -- `exec`, `--json`, `--output-schema`, `--model`, `--ephemeral`
- [Python difflib Documentation](https://docs.python.org/3/library/difflib.html) -- SequenceMatcher, unified_diff, HtmlDiff
- [SciPy pearsonr](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.pearsonr.html) -- Pearson correlation (v1.17.0)
- [SciPy spearmanr](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.spearmanr.html) -- Spearman rank correlation (v1.17.0)
- [Pydantic Documentation](https://docs.pydantic.dev/latest/) -- JSON Schema generation, model validation (v2.12.5)
- [deskew PyPI](https://pypi.org/project/deskew/) -- Evaluated and rejected: requires scikit-image
- [OpenCV Hough Transform](https://felix.abecassis.me/2011/09/opencv-detect-skew-angle/) -- Skew detection implementation pattern
- [claude-agent-sdk PyPI](https://pypi.org/project/claude-agent-sdk/) -- Evaluated and rejected: bundles CLI binary, user has own install

---
*Stack research for: scholardoc-ocr v3.0 Diagnostic Intelligence & Evaluation*
*Researched: 2026-02-17*
