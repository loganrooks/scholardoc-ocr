---
phase: 08-robustness
plan: 01
subsystem: logging
tags: [multiprocessing, logging, QueueHandler, macOS]
dependency-graph:
  requires: []
  provides: [multiprocess-logging-module]
  affects: [08-02, 08-03]
tech-stack:
  added: []
  patterns: [QueueHandler/QueueListener for fork-safe logging]
key-files:
  created:
    - src/scholardoc_ocr/logging_.py
    - tests/test_logging.py
  modified: []
decisions:
  - id: LOG-001
    decision: "Use multiprocessing.Queue with QueueHandler/QueueListener pattern"
    reason: "Fork+logging is broken on macOS; queue-based transport avoids handler I/O in workers"
metrics:
  duration: "~2 minutes"
  completed: 2026-02-02
---

# Phase 08 Plan 01: Multiprocess Logging Infrastructure Summary

**QueueHandler/QueueListener logging module with per-worker file handlers for fork-safe macOS operation.**

## What Was Built

Created `src/scholardoc_ocr/logging_.py` with three public functions:

- `setup_main_logging(log_dir, verbose)` — creates mp.Queue + QueueListener dispatching to console and optional RotatingFileHandler
- `worker_log_initializer(log_queue, log_dir)` — ProcessPoolExecutor initializer that adds QueueHandler + optional per-worker FileHandler
- `stop_logging(listener)` — idempotent listener shutdown

## Key Implementation Details

- Uses `multiprocessing.Queue` (not `queue.Queue`) for spawn-context safety on macOS
- Console format: `%(asctime)s | %(levelname)s | %(name)s | %(message)s`
- Pipeline-level log: `{log_dir}/pipeline.log` (RotatingFileHandler, 10MB, 3 backups)
- Worker-level logs: `{log_dir}/worker_{pid}.log`
- QueueListener started immediately on setup, must be stopped in finally block

## Tests

5 tests in `tests/test_logging.py`, all passing:

1. Return types verification (Queue, QueueListener)
2. QueueHandler attachment to root logger
3. Cross-process log delivery via ProcessPoolExecutor (full integration)
4. Per-worker log file creation with PID prefix
5. stop_logging idempotency

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed test pickling error with mp.Queue in spawn context**

- **Found during:** Task 2
- **Issue:** Tests passed mp.Queue as argument to `pool.submit()`, which fails on macOS spawn context because Queue objects can only be shared via inheritance (initializer args)
- **Fix:** Restructured tests to pass queue via `ProcessPoolExecutor(initializer=..., initargs=...)` instead of `pool.submit()` arguments
- **Files modified:** tests/test_logging.py

## Commits

| Hash | Message |
|------|---------|
| 6f041fa | feat(08-01): create multiprocess logging module |
| c5c835d | test(08-01): add unit tests for multiprocess logging |
