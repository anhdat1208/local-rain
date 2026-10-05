# Task 2 Report: nearest-rain deferred motion

**Branch:** `feat/radar-nearest-rain-latency`  
**Date:** 2026-10-05  
**Status:** DONE

## Summary

Implemented the nearest-rain fast path so the first cold request computes the current
rain hit and cloud cover without awaiting multi-frame motion. It returns
`motionPending: true` and writes a 90-second Redis warm marker. A follow-up request
with that marker computes shared motion once, clears the marker, caches velocity,
and returns `motionPending: false`.

Pending answer-cache entries are deliberately bypassed. Without this, the first
response's two-minute answer cache would prevent the second request from reaching
the warm-marker refinement branch.

## TDD

### RED

Created `apps/api/tests/test_nearest_rain_fast_path.py` with tests covering:

- first cold request skips `_shared_motion_context`;
- second request with a warm marker builds motion and clears the marker;
- warm-marker key, TTL, Redis read, and Redis delete behavior;
- answer-cache namespace is `nearest-rain:v23`.

The bare command first failed during collection because local Python 3.10 lacks
`datetime.UTC`. Re-running with the same local-only UTC shim used by Task 1
collected all three tests and produced three expected failures because the warm
helper methods did not exist.

### GREEN

Implemented:

- `NearestRainResponse.motion_pending` with alias `motionPending`, default `False`;
- `NearestRainResponse.motionPending?: boolean` in the shared TypeScript interface;
- Redis warm key `rain-velocity:warm:v1:{unix}:{lat3}:{lng3}` with 90-second TTL;
- cached-velocity, warm-refine, and first-cold branches in `find_nearest`;
- propagation of `motion_pending` through normal and empty responses;
- answer-cache key bump from `v22` to `v23`;
- pending answer-cache bypass so the follow-up request can refine motion.

## Verification

Focused verification command (with local Python 3.10 UTC shim):

```powershell
$env:PYTHONPATH='.'; python -c "import datetime; datetime.UTC = datetime.timezone.utc; import pytest; raise SystemExit(pytest.main(['tests/test_nearest_rain_fast_path.py', 'tests/test_radar_tile_fast_path.py', 'tests/test_clutter_mask.py', '-v']))"
```

Result: **23 passed**, 2 pre-existing Pillow deprecation warnings.

Additional checks:

- `git diff --check`: passed.
- IDE diagnostics for all four changed files: no errors.
- Direct imports of the modified Python schema/service: passed with UTC shim.
- Full API suite was attempted but collection stopped because local environment
  lacks the optional/runtime `psycopg` package.
- Shared TypeScript typecheck was attempted but local dependencies are not
  installed (`tsc` unavailable).

## Commit

- `03a463b` — `perf: defer nearest-rain motion until the refine request`

## Concerns

No blocking implementation concerns. Environment-only verification gaps remain:
the repository requires Python 3.12+, while this machine has Python 3.10, and the
local API/Node dependency sets are incomplete. The requested and adjacent radar
test suites pass with the Task 1 UTC compatibility shim.

## Important review finding follow-up

Isolated failures from `_shared_motion_context` in the warm/refine branch so the
nearest-rain card still returns from the independently completed hit and cloud
work. A failed warm attempt now uses no velocity, returns `motionPending: false`,
and clears the Redis warm marker in `finally` to avoid retry loops.

Added `test_motion_warm_failure_still_returns_valid_response`, verified it failed
with the original exception propagation, then passed after the fix.

Focused verification:

```powershell
$env:PYTHONPATH='.'; python -c "import datetime; datetime.UTC = datetime.timezone.utc; import pytest; raise SystemExit(pytest.main(['tests/test_nearest_rain_fast_path.py', '-v']))"
```

Result: **4 passed**. `git diff --check` passed and IDE diagnostics reported no
errors in the modified service and test files.
