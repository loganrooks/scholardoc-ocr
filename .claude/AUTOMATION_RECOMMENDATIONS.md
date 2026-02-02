# Claude Code Automation Recommendations for scholardoc-ocr

## Codebase Profile

- **Language**: Python >=3.11, <3.14
- **Build**: hatchling (src layout)
- **Linter**: ruff (line-length 100, rules: E, F, I, N, W)
- **Testing**: pytest
- **Key Libraries**: ocrmypdf, pymupdf, marker-pdf, rich
- **Entry point**: `ocr` CLI command via `scholardoc_ocr.cli:main`
- **Architecture**: 4-module pipeline (cli, pipeline, processor, quality)

---

## 1. Hooks

### 1a. Ruff Auto-Lint on Edit

See `HOOK_SETUP.md` for full details and design decisions.

**What it does**: Runs `ruff check --fix` and `ruff format` on any Python file after Claude edits or writes it.

**Add to `.claude/settings.json`**:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "if echo \"$CLAUDE_FILE_PATH\" | grep -q '\\.py$'; then ruff check --fix --quiet \"$CLAUDE_FILE_PATH\" 2>/dev/null; ruff format --quiet \"$CLAUDE_FILE_PATH\" 2>/dev/null; fi",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

**Why this matters**: The project has strict ruff rules configured. Without this hook, Claude may produce code that passes logically but fails `ruff check` or `ruff format --check`, requiring a manual cleanup pass. The hook eliminates that round-trip entirely.

### 1b. Block Lock/Generated File Edits

**What it does**: Prevents Claude from editing files that should never be manually modified — `.egg-info` directories, lock files, and build artifacts.

**Add to the same `hooks` block in `.claude/settings.json`**:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "echo \"$CLAUDE_FILE_PATH\" | grep -qE '(\\.egg-info/|__pycache__/|dist/|build/)' && echo 'BLOCK: Do not edit generated/build files' && exit 1 || exit 0",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

**Why this matters**: This is a `PreToolUse` hook — it runs **before** the edit and blocks it if the path matches. The project uses hatchling which generates `.egg-info` directories. Claude might try to modify these during troubleshooting. The hook prevents that silently. The pattern also covers `__pycache__`, `dist/`, and `build/` which are all generated artifacts.

**Design decision — why these paths specifically**: These are the standard Python build artifacts for a hatchling/pip project. No `.lock` files exist in this project (no pip-compile or poetry), so we match on directory patterns instead.

### Combined settings.json

The full file with both hooks and existing plugins:

```json
{
  "enabledPlugins": {
    "ralph-loop@claude-plugins-official": true,
    "serena@claude-plugins-official": true,
    "claude-code-setup@claude-plugins-official": true
  },
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "echo \"$CLAUDE_FILE_PATH\" | grep -qE '(\\.egg-info/|__pycache__/|dist/|build/)' && echo 'BLOCK: Do not edit generated/build files' && exit 1 || exit 0",
            "timeout": 5000
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "if echo \"$CLAUDE_FILE_PATH\" | grep -q '\\.py$'; then ruff check --fix --quiet \"$CLAUDE_FILE_PATH\" 2>/dev/null; ruff format --quiet \"$CLAUDE_FILE_PATH\" 2>/dev/null; fi",
            "timeout": 10000
          }
        ]
      }
    ]
  }
}
```

---

## 2. MCP Servers

### 2a. context7 — Live Documentation Lookup

**What it does**: Provides Claude with up-to-date documentation for libraries by fetching it on demand, rather than relying on training data which may be outdated.

**Install**:
```bash
claude mcp add context7 -- npx -y @upstash/context7-mcp@latest
```

**Why this matters for scholardoc-ocr**: The project depends on three libraries with non-trivial APIs:

- **ocrmypdf** — wraps Tesseract with many options for deskewing, language selection, output type. The API surface is large and version-dependent.
- **PyMuPDF (fitz)** — the PDF manipulation library used in `processor.py` for page extraction/replacement. Its API changed significantly between major versions (renamed from `fitz` to `pymupdf` namespace).
- **marker-pdf** — the Surya/Marker OCR wrapper. This is a newer library with a smaller community, meaning Claude's training data likely has limited or outdated coverage.

context7 lets Claude pull current docs for these libraries mid-conversation, reducing hallucinated API calls.

**Design decision — why not just rely on training data**: marker-pdf in particular is actively developed and its API has changed across versions. A `>=1.0.0` pin means the project tracks the latest, so current docs are essential.

---

## 3. Skills

### 3a. `/gen-test` — Generate pytest Tests

**What it does**: A user-invokable skill that generates pytest tests following the project's conventions. Encodes knowledge about how to mock PDF processing, quality analysis, and pipeline orchestration.

**Create** `.claude/skills/gen-test/SKILL.md`:

```yaml
---
name: gen-test
description: Generate pytest tests for scholardoc-ocr modules
disable-model-invocation: true
---
```

```markdown
# Test Generation Skill

Generate pytest tests for the scholardoc-ocr project.

## Conventions

- Tests go in `tests/` at the project root
- Test files are named `test_<module>.py` matching `src/scholardoc_ocr/<module>.py`
- Use pytest fixtures, not unittest classes
- Mock external dependencies: ocrmypdf, marker, pymupdf
- Use `tmp_path` fixture for any file I/O
- Test quality thresholds with parametrize for edge cases

## Module-Specific Guidance

### quality.py tests
- Test `QualityAnalyzer` with known garbled text samples and known good text
- Test that whitelisted philosophical terms (German, French, Greek) are not flagged
- Parametrize across threshold values

### processor.py tests
- Mock `ocrmypdf.ocr()` and marker's processing functions
- Test `PDFProcessor` methods individually
- Use fixture PDFs or mock PyMuPDF document objects

### pipeline.py tests
- Mock `PDFProcessor` and `QualityAnalyzer` entirely
- Test the two-phase orchestration logic
- Test that Surya is only invoked for pages below threshold
- Test parallel execution with multiple files

### cli.py tests
- Use `click.testing.CliRunner` or `argparse` equivalent
- Test argument parsing and `PipelineConfig` construction
- Test default values match documented defaults
```

**Why `disable-model-invocation: true`**: This is a user-only skill. Test generation should be intentional — you invoke it with `/gen-test` when you want tests, not something Claude decides to do on its own mid-task. Generating tests has side effects (new files) and should be explicitly requested.

**Why a skill and not just asking Claude to write tests**: The skill encodes project-specific knowledge about mocking strategies, fixture patterns, and module-specific testing approaches. Without it, Claude would need to rediscover these patterns each session by reading existing tests and source code. The skill front-loads that context.

### 3b. `/ocr-debug` — Debug OCR Pipeline Issues

**What it does**: A user-invokable skill for diagnosing OCR quality issues — helps investigate why specific pages fail quality checks or produce garbled output.

**Create** `.claude/skills/ocr-debug/SKILL.md`:

```yaml
---
name: ocr-debug
description: Debug OCR quality issues for specific PDFs or pages
disable-model-invocation: true
---
```

```markdown
# OCR Debug Skill

Help diagnose OCR quality issues in the scholardoc-ocr pipeline.

## When invoked

The user will describe an OCR quality problem (garbled output, wrong language detection, pages unnecessarily sent to Surya, etc.).

## Diagnostic Steps

1. **Identify the module**: Determine if the issue is in Tesseract output (processor.py), quality scoring (quality.py), or pipeline routing (pipeline.py)
2. **Check quality thresholds**: Read the QualityAnalyzer logic and the current threshold. Determine if the threshold is too aggressive or too lenient for the described case
3. **Check whitelist coverage**: If valid terms are being flagged as garbled, check if they need to be added to the academic term whitelist in quality.py
4. **Check language config**: Verify the Tesseract and Surya language lists match the document's languages
5. **Suggest fixes**: Propose specific code changes, threshold adjustments, or whitelist additions

## Key files to read
- `src/scholardoc_ocr/quality.py` — scoring logic and whitelist
- `src/scholardoc_ocr/processor.py` — OCR invocation parameters
- `src/scholardoc_ocr/pipeline.py` — phase 1/phase 2 routing logic
```

**Why this skill**: OCR quality debugging is a recurring task for this project — the quality analyzer uses heuristics (regex-based garbled text detection, academic term whitelists) that need tuning as new documents are processed. This skill gives Claude a structured diagnostic approach instead of ad-hoc exploration each time.

---

## 4. Subagents

### 4a. Security Reviewer

**What it does**: A specialized agent that reviews code changes for security issues, run in parallel with other work.

**Create** `.claude/agents/security-reviewer.md`:

```markdown
# Security Reviewer

You are a security-focused code reviewer for a Python OCR pipeline that processes user-supplied PDF files.

## Focus Areas

### File Path Safety
- Check for path traversal vulnerabilities in file handling
- Verify that output paths are properly sanitized
- Ensure temporary files are created securely (using `tempfile` module)

### Command Injection
- The pipeline shells out to ocrmypdf (which wraps Tesseract)
- Verify that user-supplied filenames and paths are not interpolated into shell commands unsafely
- Check for proper use of subprocess with argument lists (not shell=True with string interpolation)

### PDF Processing Safety
- PyMuPDF parses untrusted PDFs — check for proper error handling around malformed inputs
- Verify that Marker/Surya model loading doesn't execute arbitrary code from PDF content

### Resource Exhaustion
- Check that parallel processing (ProcessPoolExecutor) has proper bounds
- Verify timeout handling for OCR operations on malformed PDFs
- Check for unbounded memory usage when processing large documents

## Review Process
1. Read the changed files
2. Identify security-relevant code paths
3. Report findings with severity (Critical / High / Medium / Low)
4. Suggest specific fixes for each finding
```

**Why this matters**: The pipeline processes arbitrary user-supplied PDF files and shells out to external tools. PDF files are a well-known attack vector. The processor.py module interacts with ocrmypdf (which invokes Tesseract as a subprocess) and PyMuPDF (a C-extension PDF parser). Both are points where malformed input could cause issues. A security reviewer subagent can be invoked after any change to processor.py or pipeline.py to catch regressions.

**When to invoke**: Run manually after changes to `processor.py` or `pipeline.py`, or when adding new file I/O paths. Not something that needs to run on every edit — that would be excessive for a project this size.

---

## 5. Plugins

### 5a. anthropic-agent-skills

**What it does**: A bundle of general-purpose skills maintained by Anthropic, including commit workflows, code review helpers, and other common tasks.

**Install**: Add to `.claude/settings.json`:

```json
{
  "enabledPlugins": {
    "anthropic-agent-skills@claude-plugins-official": true
  }
}
```

**Why this matters**: Provides baseline productivity skills (structured commits, PR descriptions, etc.) without needing to build custom skills for common workflows. Complements the project-specific skills above.

**Design decision — why not more plugins**: The project is a focused Python CLI tool, not a web app or API service. Most available plugins target web development workflows (frontend-design, mcp-builder). The general-purpose bundle is the only one that adds value here without introducing irrelevant noise.

---

## Implementation Priority

Ordered by impact-to-effort ratio:

1. **Ruff auto-lint hook** — Immediate, high-frequency benefit. Every edit gets auto-formatted.
2. **Block generated files hook** — Quick safety guard, prevents wasted effort.
3. **context7 MCP server** — One command to install, ongoing benefit for API accuracy.
4. **gen-test skill** — Saves significant time when expanding test coverage.
5. **ocr-debug skill** — Valuable for ongoing quality tuning work.
6. **Security reviewer subagent** — Important but lower frequency; invoke after security-relevant changes.
7. **anthropic-agent-skills plugin** — Nice to have for general workflow polish.

---

## How to Implement

Ask Claude to implement any of these by referencing this document. For example:

- "Set up the hooks from AUTOMATION_RECOMMENDATIONS.md"
- "Create the gen-test skill from AUTOMATION_RECOMMENDATIONS.md"
- "Install the context7 MCP server"

Each section is self-contained with the exact files to create or modify.
