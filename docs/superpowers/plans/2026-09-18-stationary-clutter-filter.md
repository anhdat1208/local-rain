# Stationary Clutter Filter Implementation Plan

> **For agentic workers:** Execute task-by-task. Steps use checkbox syntax.

**Goal:** Hide multi-hour stationary RainViewer echoes from map + advice (2h threshold).

**Architecture:** Redis-backed `ClutterTracker` on motion grid; nearest-rain observes fields; tile filter zeros clutter pixels.

**Tech Stack:** Python, Redis, Pillow, pytest

**Global Constraints:** Fail-open on Redis errors; `STATIONARY_SECONDS = 7200`; grid `0.03°`; no new Vercel env.

---

### Task 1: ClutterTracker module + unit tests

**Files:**
- Create: `apps/api/app/services/clutter_track.py`
- Test: `apps/api/tests/test_clutter_track.py`

- [ ] Tests for cell index, mature clutter after 2h credit, motion reset, fail-open
- [ ] Implement `ClutterTracker` with Redis keys `clutter:cell:v1:{iy}:{ix}` + set `clutter:active:v1`

### Task 2: Wire nearest-rain + advice

**Files:**
- Modify: `apps/api/app/services/nearest_rain.py`
- Modify: `apps/api/app/services/advice_rules.py`
- Test: `apps/api/tests/test_advice_clutter.py`

- [ ] Observe field after motion; credit 2h when `velocity is None`
- [ ] Clutter hits → not raining_here, clutter copy, bump cache `v22`

### Task 3: Map tile filter

**Files:**
- Modify: `apps/api/app/services/radar_dbz.py`
- Modify: `apps/api/app/services/radar.py`
- Test: `apps/api/tests/test_clutter_tile_filter.py`

- [ ] Zero clutter pixels after dBZ filter; bump tile cache `v5`

### Task 4: Verify

- [ ] `pytest apps/api/tests/test_clutter*.py apps/api/tests/test_advice_clutter.py -v`
