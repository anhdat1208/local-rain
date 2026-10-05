# Radar tile + nearest-rain latency

## Goal

Cut cold-path latency on Vercel without rewriting the stack (stay Python/FastAPI).

| Metric | Target (cold, typical) | Notes |
|--------|------------------------|--------|
| Radar/map tile first bytes | ~3s | Fast path may omit clutter briefly |
| nearest-rain card usable | ~3–5s | Distance/advice first; ETA may refine |
| Feeling of hang | Never ~10s+ for first paint | Hard SLA not required if these hold |

Warm cache paths should stay as fast as today (or better).

## Decisions (locked)

- Approach: **fast path + refine** (not Node rewrite, not long-running warm workers, not client-only RainViewer).
- Map tiles: **hybrid by tile `z`** — street-relevant zooms fast-first; wide zooms keep full clutter when cheap.
- nearest-rain: **hybrid** — first response prioritizes hit/advice; motion/ETA fills from velocity cache or a follow-up refresh.
- Success bar: option **B** (~3s tiles, ~3–5s card).

## Out of scope

- Migrating API to Node.js
- Changing host (still Vercel serverless)
- Rewriting rain-detection science (dBZ thresholds, motion correlation math)
- Clouds/Himawari pipeline (unless a shared HTTP helper change is trivial)

## Architecture

```
MapLibre tile request
  → GET /api/radar/tiles/{t}/{z}/{x}/{y}.png
  → Redis full filtered? return
  → Redis fast filtered? return
  → fetch 1× RainViewer raw
  → if z >= 6 (same threshold as CLUTTER_MIN_ZOOM): filter(dBZ) → return fast + cache
       (clutter refine on next request / when mask ready)
  → else: clutter_mask (up to 9 frames) → filter → return full

nearest-rain
  → frames + Redis answer cache
  → parallel: nearest hit (ring) + clouds sample
  → velocity cache hit? attach ETA/direction
  → else: return card without blocking multi-frame motion
  → later request / background-safe path fills velocity cache
  → FE stale+refresh already paints then updates
```

## Tile path

### Behavior

1. **Full cache hit** (`radar:tile:v6:…` or successor key): return as today; long TTL (~900s).
2. **Fast cache hit** (new key namespace): return filtered-without-clutter (or with peek-only mask); short TTL (~45–60s).
3. **Miss, `z >= 6`** (align with existing `CLUTTER_MIN_ZOOM`):
   - Fetch/cache raw tile (existing `radar:raw:v1:…`).
   - `peek_clutter_mask` only — never block on 9-frame build for the response.
   - `filter_tile_below_dbz(..., smooth=True)` → respond.
   - Write fast cache.
   - Optionally kick a best-effort mask warm: if the platform allows fire-and-forget without delaying the response, build `clutter_mask` and write full filtered cache; otherwise rely on the next tile request after mask appears in Redis.
4. **Miss, `z < 6`**: keep current full clutter path (few tiles, amplification smaller).

### Cache keys

- Keep raw + clutter hot/mask keys as today.
- Add explicit fast filtered key, e.g. `radar:tile:fast:v1:{unix}:{z}:{x}:{y}` (no newest/clutter generation in key — it is intentionally imperfect).
- Full filtered key stays generation-aware (`newest`) so scrubbing timeline stays consistent once refined.

### HTTP caching

- Fast responses: `Cache-Control: public, max-age=45` (or similar short).
- Full responses: keep `max-age=120` (or current).
- FE prefetch may re-hit after short TTL to pick up cleaned tiles naturally; no mandatory new query param unless short TTL proves insufficient.

### Correctness trade-off

Street zoom may briefly show parked strong echoes that clutter would remove. Acceptable for a few seconds; refine path must not regress warm correctness.

## nearest-rain path

### Behavior

1. Resolve current frame + answer cache (unchanged idea; bump cache key version when response shape/semantics change).
2. Always compute (parallel):
   - nearest hit (existing ring scan; clutter compute on center tile only, peek elsewhere — already largely true)
   - cloud cover sample
3. Velocity / ETA:
   - If regional velocity cache hit → attach motion as today.
   - If miss → **do not** await `_shared_motion_context` on the critical path.
   - Return card with distance/advice/`rainingHere`; motion fields use safe empty/unknown defaults already understood by FE, or a light single-frame fallback if one already exists without extra upstream fan-out.
4. Refinement:
   - Prefer FE’s existing stale-then-refresh: second `/api/nearest-rain` within the session should hit velocity cache after a non-blocking warm.
   - Warm strategy: after returning fast response is not reliable on Vercel (function freeze). Prefer **inline warm only when cheap**, else **lazy warm on the next API call** that already has frames (e.g. rain-vectors, second nearest-rain, or tile traffic sharing raw cache). Practical MVP: first cold nearest-rain skips motion; a follow-up client refresh (~1–2s later or after map settle) rebuilds motion once and caches velocity for ~TTL.

### FE (minimal)

- Keep sessionStorage stale paint for nearest-rain.
- Ensure a single automatic refresh after first cold success when motion was incomplete (detect via null/zero ETA fields or an explicit `motionPending`-style flag if needed). Prefer reusing existing fields over new API surface; add a boolean only if FE cannot tell.

### location

- Not a primary rewrite. Nominatim is already timeout-bound (4s) + Redis. No change unless profiling shows it on the critical waterfall; then ensure FE does not block map tiles on location label.

## Error handling

- Upstream RainViewer failure on fast path: same 502/empty behavior as today for that tile.
- Partial clutter window: continue declining mask (no over-suppress); fast path still returns dBZ-filtered tile.
- Motion warm failure: card remains valid without ETA; do not fail the whole nearest-rain request.
- Redis down: degrade to uncached fast path; still avoid 9-frame block on street tiles.

## Testing

- Unit: clutter peek vs compute not called on fast tile path for `z >= 6`.
- Unit: nearest-rain with empty velocity cache returns without calling multi-frame motion builder (mock).
- Unit: nearest-rain with velocity cache still attaches ETA.
- Existing clutter/filter tests remain green for full path (`z < 6` or explicit full filter helper).
- Manual: cold load HCMC street zoom — tiles visible under ~3s; card under ~5s; brief clutter flash OK; refresh cleans/refines.

## Rollout

- Branch: `feat/radar-nearest-rain-latency` (from `master`).
- Deploy onto existing Vercel API project (overwrite). Same env/Redis.
- Rollback: revert deploy; cache key namespaces are additive so old code ignores fast keys.

## Success criteria

- Cold street viewport no longer sits blank ~10s waiting on clutter fan-out.
- Cold nearest-rain card shows actionable rain/distance within ~5s.
- Warm paths and clutter correctness after refine remain acceptable in HCMC parked-echo scenarios.
