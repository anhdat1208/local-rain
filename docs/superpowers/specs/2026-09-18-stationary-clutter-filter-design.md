# Design: Stationary radar clutter filter (map + advice)

## Problem

RainViewer mosaics around HCMC can paint strong echoes (≥45–55 dBZ) that sit for **days** with little real motion. Local Rain remaps those to purple and can mark “mưa tại chỗ” even when the ground is dry. App cache (minutes–2h) is not the cause; the upstream echo is sticky.

## Goal

Treat **long-lived, nearly stationary** high-dBZ cells as clutter:

1. **Advice / nearest-rain** — do not claim raining-here; lower chance; clutter-aware copy.
2. **Map overlay** — zero those pixels in filtered tiles so purple blobs disappear.

Threshold agreed with product: **2 continuous hours** of hot + no meaningful motion.

## Approach (B)

Redis-backed persistence on the existing motion grid (`MOTION_GRID_DEG ≈ 0.03°` ≈ 3 km), updated from nearest-rain / motion analysis, consumed by tile filter + advice.

### Detection rules

For each hot grid cell (peak dBZ ≥ `DETECT_MIN_DBZ` 35):

| Event | Effect on Redis track |
|-------|------------------------|
| Still hot, local speed &lt; ~3 km/h (or no usable velocity) | Keep / extend `stationary_since` |
| Clear motion (≥ ~3 km/h) or field fingerprint changes strongly | Reset track (treat as weather) |
| Echo gone (cold) | Decay / delete track |

Mark cell **clutter** when:

`now - stationary_since >= 2 hours` **and** cell is still hot on the current frame.

Redis key shape (example): `clutter:cell:v1:{ilat}:{ilon}`  
Value: JSON `{stationary_since, last_hot, last_moved, peak_dbz}`  
TTL: ~7 days (auto-expire abandoned cells).

Fail-open: Redis errors → no suppression (prefer false rain over hiding real rain).

### Who updates Redis

Primary: `NearestRainService` motion path after baselines/velocity for the local field (and rain-vectors when it shares that context).  
No separate cron required on serverless; traffic that already hits analysis warms the tracks. Map-only viewers may lag until someone nearby triggers analysis — acceptable for v1; optional later: light update from tile path for z=7 Vietnam tiles only.

### Advice wiring

- Before `is_raining_here` / `build_advice`: if nearest hit’s cell (or support cluster majority) is clutter → force `raining_here=false`, cap chance, use clutter copy (extend existing speckle/clutter strings).
- Bump nearest-rain response cache key version so old “wet” answers are not sticky.

### Map wiring

- Extend tile filter (after dBZ ≥35 pass): drop pixels whose lat/lon fall in a clutter cell.
- Load clutter cell set from Redis with a short in-process / Redis cache (e.g. 60–120s) so every pixel does not hit Redis.
- Bump filtered tile cache key version (`radar:tile:v5:…`) so old purple tiles are not served.

### Performance

- Clutter set for a tile: intersect tile bbox with tracked cells (or load regional set once per request).
- Pixel → grid index is O(1) math; only applied to surviving ≥35 pixels.

## Out of scope (v1)

- Multi-radar QC / dual-pol hydrometeor class.
- Client-side filtering.
- Global “always suppress HCMC District 8” hardcode.
- Background worker solely for clutter refresh.

## Tests

- Unit: track reaches 2h stationary → `is_clutter`; motion reset → not clutter.
- Unit: advice with clutter hit → not raining-here, lower pct.
- Unit: tile filter zeros pixels in clutter cells, keeps moving/non-tracked rain.
- Optional probe: Chánh Hưng coords against live Redis after synthetic age injection.

## Success criteria

- Sticky multi-hour purple AP/clutter over HCMC fades from map after tracks mature (≥2h).
- Popup stops “mưa tại chỗ / ~80%” for those cells.
- Real moving showers still paint and advise normally within the 2h window.
