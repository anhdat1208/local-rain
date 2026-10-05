## Whole-branch Important findings — 2026-10-05

### Changes

- Radar tile refinement now keeps the first high-zoom cache miss fast, then uses a fast-cache hit as the signal to await `clutter_mask`, filter the raw tile, cache the full tile, and return `kind=full`.
- Nearest-rain UI refinement now runs in a detached async task after the first card is painted, allowing `fetchNearestRain` and the page-level in-flight guard to resolve immediately.
- Added `refine` query handling from the nearest-rain router through `force_refine` in the service. The UI sends `refine=1`, so motion refinement works even when the Redis warm marker is unavailable; marker-based refinement remains intact.
- Added regression coverage for cold/fast radar behavior, forced refinement without a warm marker, and router flag forwarding.

### Verification

- Command (from `apps/api`, with the `datetime.UTC` compatibility shim):
  `python -c "import datetime; import sys; setattr(datetime, 'UTC', getattr(datetime, 'UTC', datetime.timezone.utc)); import pytest; raise SystemExit(pytest.main(['-v','tests/test_radar_tile_fast_path.py','tests/test_nearest_rain_fast_path.py','tests/test_clutter_mask.py']))"`
- Result: **26 passed, 2 pre-existing Pillow deprecation warnings in 8.82s**.
- IDE lint diagnostics: **no errors** in all changed files.
- `git diff --check`: **passed**.
- `npm run typecheck` from `apps/web`: could not run because local frontend dependencies are not installed (`nuxt` command not found).
