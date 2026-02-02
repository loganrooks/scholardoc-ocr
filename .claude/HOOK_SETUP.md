# Ruff Auto-Lint Hook Setup

## Goal

Automatically run `ruff check --fix` and `ruff format` on any file Claude edits or writes, so code always conforms to the project's ruff configuration without manual intervention.

## Current State

**`.claude/settings.json`** currently contains only plugin config:

```json
{
  "enabledPlugins": {
    "ralph-loop@claude-plugins-official": true,
    "serena@claude-plugins-official": true,
    "claude-code-setup@claude-plugins-official": true
  }
}
```

**Project ruff config** (from `pyproject.toml`):
- `line-length = 100`
- `target-version = "py311"`
- Rules: `E, F, I, N, W`

## Implementation

Replace `.claude/settings.json` with:

```json
{
  "enabledPlugins": {
    "ralph-loop@claude-plugins-official": true,
    "serena@claude-plugins-official": true,
    "claude-code-setup@claude-plugins-official": true
  },
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

## Design Decisions

### Why `PostToolUse` and not `PreToolUse`?

`PreToolUse` hooks run **before** the tool executes and can block it. That's useful for preventing edits to certain files. We want the opposite: let the edit happen, then clean it up. `PostToolUse` fires after the tool completes, which is when we want to format.

### Why match `Edit|Write` and not other tools?

These are the only two tools that modify file contents. `Bash` could also write files, but hooking into every bash command would be noisy and slow. The vast majority of Claude's code edits go through `Edit` and `Write`.

### Why filter for `.py$`?

The project only contains Python source code that ruff can process. Without the filter, ruff would error on non-Python files (markdown, toml, json) that Claude might edit, producing noisy stderr output. The `grep -q '\.py$'` guard skips non-Python files entirely.

### Why `--fix` on check and not just format?

- `ruff check --fix` auto-fixes lint issues (unused imports, import sorting via `I` rule, simple style fixes from `E` and `W` rules)
- `ruff format` handles whitespace, line length, quoting, etc.

Both are needed because they address different concerns. Check-with-fix handles logical lint; format handles style.

### Why `--quiet`?

Without `--quiet`, ruff prints every file it processes and every fix it applies. In a hook context this output would appear as hook feedback after every edit, which is distracting. Quiet mode suppresses output unless there are unfixable errors.

### Why `2>/dev/null`?

If ruff encounters a syntax error (e.g., Claude wrote incomplete code mid-edit), it emits stderr. Suppressing stderr prevents the hook from surfacing confusing error messages for transient states. The next edit will trigger the hook again, and once the code is syntactically valid, ruff will format it correctly.

### Why `timeout: 10000`?

10 seconds is generous for ruff, which typically runs in under 100ms on single files. The high timeout is a safety margin — if the file is very large or the system is under load, we don't want the hook to kill ruff prematurely and leave the file in a partial state.

### Why not separate hooks for check and format?

A single hook with both commands chained is simpler and avoids the overhead of two separate hook invocations. The commands run sequentially within the hook (`; ` separator, not `&&`), so format runs even if check finds unfixable issues.

## Verification

After updating `settings.json`, test by asking Claude to edit any `.py` file. The output should show the hook running. You can verify by intentionally having Claude write an unsorted import — ruff should auto-sort it.

## Rollback

To remove the hook, restore `settings.json` to its original state (just the `enabledPlugins` block).
