# Radar Tile + Nearest-Rain Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut cold-path latency so street radar tiles paint in ~3s and nearest-rain cards become usable in ~3–5s, using fast-path + refine without changing host or language.

**Architecture:** Radar tiles at `z >= 6` return dBZ-filtered PNG without blocking on 9-frame clutter; full filtered cache fills on a later request once masks exist. nearest-rain skips multi-frame motion on the first cold miss, returns `motionPending`, and the next client refresh builds velocity into Redis.

**Tech Stack:** Python 3.13, FastAPI, Pillow, Redis, httpx, pytest, Nuxt 4, TypeScript (`@local-rain/shared`)

## Global Constraints

- Stay on Vercel Python serverless — no Node rewrite, no long-running workers
- Targets: tile cold ~3s; nearest-rain card ~3–5s (option B from spec)
- Street tiles may briefly show parked clutter; warm/full path must stay correct
- Do not weaken dBZ map filter thresholds
- Prefer additive Redis key namespaces; bump nearest-rain answer cache version when response shape changes
- Spec: `docs/superpowers/specs/2026-10-05-radar-nearest-rain-latency-design.md`
- Branch: `feat/radar-nearest-rain-latency`

## File map

| File | Role |
|------|------|
| `apps/api/app/services/radar.py` | Fast vs full filtered tile path + cache keys |
| `apps/api/app/routers/radar.py` | `Cache-Control` differs for fast vs full |
| `apps/api/app/services/nearest_rain.py` | Skip motion once; warm on second request |
| `apps/api/app/schemas/nearest_rain.py` | Add `motionPending` |
| `packages/shared/src/index.ts` | Mirror `motionPending` |
| `apps/web/composables/useNearestRain.ts` | One automatic refresh when `motionPending` |
| `apps/api/tests/test_radar_tile_fast_path.py` | Tile fast-path unit tests |
| `apps/api/tests/test_nearest_rain_fast_path.py` | nearest-rain motion skip/warm tests |

---

### Task 1: Fast radar tile path (no clutter block at z≥6)

**Files:**
- Modify: `apps/api/app/services/radar.py`
- Modify: `apps/api/app/routers/radar.py`
- Create: `apps/api/tests/test_radar_tile_fast_path.py`

**Interfaces:**
- Consumes: `peek_clutter_mask`, `clutter_mask`, `filter_tile_below_dbz`, `get_http_client`, Redis helpers already in `RadarService`
- Produces:
  - `RadarService.get_filtered_tile(...) -> bytes` (behavior change)
  - `RadarService.get_filtered_tile_result(...) -> FilteredTileResult` **or** tuple `(bytes, kind: Literal["fast","full"])` used by router for Cache-Control
  - Constants: `FAST_TILE_CACHE_PREFIX = "radar:tile:fast:v1"`, `FAST_TILE_TTL_SECONDS = 60`, `FULL_CACHE_CONTROL = "public, max-age=120"`, `FAST_CACHE_CONTROL = "public, max-age=45"`

- [ ] **Step 1: Write failing tests**

Create `apps/api/tests/test_radar_tile_fast_path.py`:

```python
from __future__ import annotations

import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.services.clutter_mask import TILE_SIZE
from app.services.radar import RadarService


def _png() -> bytes:
    image = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (193, 0, 0, 255))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_z7_miss_uses_peek_not_full_clutter_mask() -> None:
    raw = _png()
    service = RadarService()
    redis = MagicMock()
    redis.get.return_value = None

    client = AsyncMock()
    response = MagicMock()
    response.content = raw
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    with (
        patch("app.services.radar.get_redis", return_value=redis),
        patch("app.services.radar.get_http_client", return_value=client),
        patch.object(service, "upstream_map", return_value={1_700_000_000: "https://example/{z}/{x}/{y}"}),
        patch.object(service, "newest_past_unix", return_value=1_700_000_000),
        patch.object(service, "upstream_for_frame", AsyncMock(return_value="https://example/{z}/{x}/{y}")),
        patch("app.services.radar.peek_clutter_mask", return_value=None) as peek,
        patch("app.services.radar.clutter_mask", AsyncMock()) as full_mask,
        patch("app.services.radar.filter_tile_below_dbz", return_value=raw) as filt,
    ):
        png, kind = await service.get_filtered_tile_with_kind(1_700_000_000, 7, 100, 60)

    assert kind == "fast"
    assert png == raw
    peek.assert_called_once()
    full_mask.assert_not_called()
    filt.assert_called_once()
    assert filt.call_args.kwargs.get("clutter") is None or filt.call_args.args[1:] == ()


@pytest.mark.asyncio
async def test_z5_miss_still_awaits_clutter_mask() -> None:
    raw = _png()
    service = RadarService()
    redis = MagicMock()
    redis.get.return_value = None
    mask = b"\x00" * (TILE_SIZE * TILE_SIZE // 8)

    client = AsyncMock()
    response = MagicMock()
    response.content = raw
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    with (
        patch("app.services.radar.get_redis", return_value=redis),
        patch("app.services.radar.get_http_client", return_value=client),
        patch.object(service, "upstream_map", return_value={1_700_000_000: "https://example/{z}/{x}/{y}"}),
        patch.object(service, "newest_past_unix", return_value=1_700_000_000),
        patch.object(service, "upstream_for_frame", AsyncMock(return_value="https://example/{z}/{x}/{y}")),
        patch("app.services.radar.clutter_mask", AsyncMock(return_value=mask)) as full_mask,
        patch("app.services.radar.filter_tile_below_dbz", return_value=raw),
    ):
        png, kind = await service.get_filtered_tile_with_kind(1_700_000_000, 5, 10, 20)

    assert kind == "full"
    full_mask.assert_awaited()


@pytest.mark.asyncio
async def test_full_cache_hit_skips_upstream() -> None:
    raw = _png()
    service = RadarService()
    redis = MagicMock()
    # First redis.get is full cache key
    redis.get.side_effect = [base64.b64encode(raw).decode("ascii")]

    with (
        patch("app.services.radar.get_redis", return_value=redis),
        patch("app.services.radar.get_http_client") as http,
        patch.object(service, "upstream_map", return_value={1_700_000_000: "https://example/{z}/{x}/{y}"}),
        patch.object(service, "newest_past_unix", return_value=1_700_000_000),
    ):
        png, kind = await service.get_filtered_tile_with_kind(1_700_000_000, 7, 100, 60)

    assert kind == "full"
    assert png == raw
    http.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api; python -m pytest tests/test_radar_tile_fast_path.py -v`

Expected: FAIL (import/attribute errors for `get_filtered_tile_with_kind` / missing `peek_clutter_mask` import in radar module)

- [ ] **Step 3: Implement fast path in `radar.py`**

Update imports to include `peek_clutter_mask` from `app.services.clutter_mask` and `CLUTTER_MIN_ZOOM`.

Add constants near other TTLs:

```python
FAST_FILTERED_TILE_TTL_SECONDS = 60
FAST_TILE_CACHE_PREFIX = "radar:tile:fast:v1"
```

Replace/`wrap` tile fetch with:

```python
async def get_filtered_tile(self, unix_time: int, z: int, x: int, y: int) -> bytes:
    png, _kind = await self.get_filtered_tile_with_kind(unix_time, z, x, y)
    return png

async def get_filtered_tile_with_kind(
    self, unix_time: int, z: int, x: int, y: int
) -> tuple[bytes, str]:
    if z < 0 or z > 7 or x < 0 or y < 0:
        raise ValueError("Invalid tile coordinates")

    upstreams = self.upstream_map()
    newest = self.newest_past_unix(upstreams)
    full_key = f"radar:tile:v6:{newest}:{unix_time}:{z}:{x}:{y}"
    fast_key = f"{FAST_TILE_CACHE_PREFIX}:{unix_time}:{z}:{x}:{y}"

    try:
        cached = get_redis().get(full_key)
        if cached:
            return base64.b64decode(cached), "full"
    except Exception:
        pass

    # If a peek mask already exists, promote to full filtered immediately
    peek = peek_clutter_mask(newest, z, x, y) if newest is not None else None

    upstream_template = await self.upstream_for_frame(unix_time)
    url = (
        upstream_template.replace("{z}", str(z))
        .replace("{x}", str(x))
        .replace("{y}", str(y))
    )
    raw_cache_key = f"radar:raw:v1:{unix_time}:{z}:{x}:{y}"
    raw: bytes | None = None
    try:
        cached_raw = get_redis().get(raw_cache_key)
        if cached_raw:
            raw = base64.b64decode(cached_raw)
    except Exception:
        pass

    if raw is None:
        response = await get_http_client().get(url, timeout=12.0)
        response.raise_for_status()
        raw = response.content
        try:
            get_redis().setex(
                raw_cache_key,
                TILE_CACHE_TTL_SECONDS,
                base64.b64encode(raw).decode("ascii"),
            )
        except Exception:
            pass

    use_fast = z >= CLUTTER_MIN_ZOOM and peek is None
    if use_fast:
        # Street/overzoom cold path: never await 9-frame clutter here
        try:
            cached_fast = get_redis().get(fast_key)
            if cached_fast:
                return base64.b64decode(cached_fast), "fast"
        except Exception:
            pass
        filtered = filter_tile_below_dbz(raw, clutter=None, smooth=True)
        try:
            get_redis().setex(
                fast_key,
                FAST_FILTERED_TILE_TTL_SECONDS,
                base64.b64encode(filtered).decode("ascii"),
            )
        except Exception:
            pass
        return filtered, "fast"

    mask = peek
    if mask is None and newest is not None:
        mask = await clutter_mask(
            client=get_http_client(),
            upstreams=upstreams,
            newest=newest,
            z=z,
            x=x,
            y=y,
        )

    filtered = filter_tile_below_dbz(raw, clutter=mask, smooth=True)
    try:
        get_redis().setex(
            full_key,
            FILTERED_TILE_TTL_SECONDS,
            base64.b64encode(filtered).decode("ascii"),
        )
    except Exception:
        pass
    return filtered, "full"
```

Import `CLUTTER_MIN_ZOOM` and `peek_clutter_mask` from `app.services.clutter_mask`.

- [ ] **Step 4: Wire Cache-Control in router**

In `apps/api/app/routers/radar.py`:

```python
from app.services.radar import (
    FAST_CACHE_CONTROL,
    FULL_CACHE_CONTROL,
    RadarService,
    get_radar_service,
)

# inside get_radar_tile:
png, kind = await radar_service.get_filtered_tile_with_kind(unix_time, z, x, y)
cache_control = FAST_CACHE_CONTROL if kind == "fast" else FULL_CACHE_CONTROL
return Response(
    content=png,
    media_type="image/png",
    headers={"Cache-Control": cache_control},
)
```

Add module-level strings in `radar.py`:

```python
FAST_CACHE_CONTROL = "public, max-age=45"
FULL_CACHE_CONTROL = "public, max-age=120"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd apps/api; python -m pytest tests/test_radar_tile_fast_path.py tests/test_clutter_mask.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/app/services/radar.py apps/api/app/routers/radar.py apps/api/tests/test_radar_tile_fast_path.py
git commit -m "perf: serve street radar tiles without blocking on clutter"
```

---

### Task 2: nearest-rain skip motion once + `motionPending`

**Files:**
- Modify: `apps/api/app/schemas/nearest_rain.py`
- Modify: `apps/api/app/services/nearest_rain.py`
- Modify: `packages/shared/src/index.ts`
- Create: `apps/api/tests/test_nearest_rain_fast_path.py`

**Interfaces:**
- Consumes: `_read_velocity_cache`, `_write_velocity_cache`, `_shared_motion_context`, `_find_nearest_hit`, Redis
- Produces:
  - `NearestRainResponse.motion_pending: bool` alias `motionPending` (default `False`)
  - Redis marker `rain-velocity:warm:v1:{unix}:{lat3}:{lng3}` TTL 90s — set when first cold skips motion; cleared implicitly when velocity cache is written
  - Answer cache key bump: `nearest-rain:v23:...` (from `v22`)

Logic in `find_nearest` after frames/current/cache miss:

```python
velocity_key = self._velocity_cache_key(current, latitude, longitude)
cached_velocity = self._read_velocity_cache(velocity_key)
warm_key = self._velocity_warm_key(current, latitude, longitude)
motion_pending = False

if cached_velocity is not None:
    current_hit, clouds = await asyncio.gather(...)
    velocity = cached_velocity.velocity
elif self._velocity_warm_requested(warm_key):
    # Second (or refine) request: pay for multi-frame motion once
    current_hit, motion_ctx, clouds = await asyncio.gather(
        self._find_nearest_hit(...),
        self._shared_motion_context(...),
        self._clouds_service.sample_cover(...),
    )
    velocity = motion_ctx.velocity
    self._clear_velocity_warm(warm_key)
else:
    # First cold: skip motion fan-out
    current_hit, clouds = await asyncio.gather(
        self._find_nearest_hit(...),
        self._clouds_service.sample_cover(...),
    )
    velocity = None
    motion_pending = True
    self._mark_velocity_warm(warm_key)
```

Pass `motion_pending` into `_build_response` / set on the model before cache write.

Warm helpers:

```python
def _velocity_warm_key(self, current, latitude, longitude) -> str:
    return (
        f"rain-velocity:warm:v1:{current.unix_time}:"
        f"{round(latitude, 3)}:{round(longitude, 3)}"
    )

def _velocity_warm_requested(self, key: str) -> bool:
    try:
        return bool(get_redis().get(key))
    except Exception:
        return False

def _mark_velocity_warm(self, key: str) -> None:
    try:
        get_redis().setex(key, 90, "1")
    except Exception:
        return

def _clear_velocity_warm(self, key: str) -> None:
    try:
        get_redis().delete(key)
    except Exception:
        return
```

Schema addition:

```python
motion_pending: bool = Field(default=False, alias="motionPending")
```

Shared TS:

```typescript
motionPending?: boolean;
```

- [ ] **Step 1: Write failing tests**

```python
# apps/api/tests/test_nearest_rain_fast_path.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.nearest_rain import NearestRainResponse
from app.schemas.radar import RadarFrameSchema, RadarResponse
from app.services.nearest_rain import NearestRainService


def _frames() -> RadarResponse:
    return RadarResponse(
        frames=[
            RadarFrameSchema(
                timestamp="2026-10-05T00:00:00+00:00",
                unix_time=1_700_000_000,
                tile_url_template="https://api.example/api/radar/tiles/1700000000/{z}/{x}/{y}.png",
            )
        ],
        generated_at="2026-10-05T00:00:00+00:00",
        host="https://example",
    )


@pytest.mark.asyncio
async def test_first_cold_skips_shared_motion_context() -> None:
    service = NearestRainService()
    service._radar_service = MagicMock()
    service._radar_service.get_radar_frames = AsyncMock(return_value=_frames())
    service._radar_service.upstream_for_frame = AsyncMock(return_value="https://rv/{z}/{x}/{y}")
    service._radar_service.upstream_map = MagicMock(return_value={1_700_000_000: "https://rv/{z}/{x}/{y}"})
    service._clouds_service = MagicMock()
    service._clouds_service.sample_cover = AsyncMock(
        return_value=MagicMock(ok=True, cover_pct=10, sky_state="clear")
    )

    with (
        patch.object(service, "_read_cache", return_value=None),
        patch.object(service, "_read_velocity_cache", return_value=None),
        patch.object(service, "_velocity_warm_requested", return_value=False),
        patch.object(service, "_mark_velocity_warm") as mark,
        patch.object(service, "_find_nearest_hit", AsyncMock(return_value=None)) as hit,
        patch.object(service, "_shared_motion_context", AsyncMock()) as motion,
        patch.object(service, "_write_cache"),
        patch("app.services.nearest_rain.get_http_client", return_value=MagicMock()),
    ):
        result = await service.find_nearest(10.77, 106.70, lang="vi")

    assert result.motion_pending is True
    motion.assert_not_called()
    hit.assert_awaited()
    mark.assert_called_once()


@pytest.mark.asyncio
async def test_second_request_builds_motion_when_warm_marked() -> None:
    service = NearestRainService()
    service._radar_service = MagicMock()
    service._radar_service.get_radar_frames = AsyncMock(return_value=_frames())
    service._radar_service.upstream_for_frame = AsyncMock(return_value="https://rv/{z}/{x}/{y}")
    service._radar_service.upstream_map = MagicMock(return_value={1_700_000_000: "https://rv/{z}/{x}/{y}"})
    service._clouds_service = MagicMock()
    service._clouds_service.sample_cover = AsyncMock(
        return_value=MagicMock(ok=True, cover_pct=10, sky_state="clear")
    )
    motion_ctx = MagicMock(velocity=(0.01, -0.02))

    with (
        patch.object(service, "_read_cache", return_value=None),
        patch.object(service, "_read_velocity_cache", return_value=None),
        patch.object(service, "_velocity_warm_requested", return_value=True),
        patch.object(service, "_clear_velocity_warm") as clear,
        patch.object(service, "_find_nearest_hit", AsyncMock(return_value=None)),
        patch.object(service, "_shared_motion_context", AsyncMock(return_value=motion_ctx)) as motion,
        patch.object(service, "_write_cache"),
        patch("app.services.nearest_rain.get_http_client", return_value=MagicMock()),
    ):
        result = await service.find_nearest(10.77, 106.70, lang="vi")

    assert result.motion_pending is False
    motion.assert_awaited()
    clear.assert_called_once()
```

Adjust mocks if `_build_response` needs richer cloud sample attributes — mirror fields used in `_build_response` / `CloudCoverSample`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api; python -m pytest tests/test_nearest_rain_fast_path.py -v`

Expected: FAIL (`motion_pending` missing / warm helpers missing)

- [ ] **Step 3: Implement schema + service + shared type**

Apply schema field, cache key bump `v22` → `v23`, warm-marker helpers, and `find_nearest` branch above. Ensure `_build_response` accepts/sets `motion_pending`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd apps/api; python -m pytest tests/test_nearest_rain_fast_path.py tests/test_clutter_mask.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/app/schemas/nearest_rain.py apps/api/app/services/nearest_rain.py packages/shared/src/index.ts apps/api/tests/test_nearest_rain_fast_path.py
git commit -m "perf: defer nearest-rain motion until the refine request"
```

---

### Task 3: FE one-shot refresh when `motionPending`

**Files:**
- Modify: `apps/web/composables/useNearestRain.ts`

**Interfaces:**
- Consumes: `NearestRainResponse.motionPending`
- Produces: at most one automatic follow-up `apiFetch` per `fetchNearestRain` call when first response has `motionPending === true`

- [ ] **Step 1: Update `fetchNearestRain`**

```typescript
async function fetchNearestRain(latitude: number, longitude: number): Promise<void> {
  const stale = readStale(latitude, longitude);
  if (stale) {
    store.setResult(stale);
  } else {
    store.setLoading(true);
  }
  store.setError(null);
  try {
    const data = await apiFetch<NearestRainResponse>("/api/nearest-rain", {
      query: { lat: latitude, lng: longitude, lang: locale.value },
      timeout: 16_000,
    });
    store.setResult(data);
    writeStale(latitude, longitude, data);

    if (data.motionPending) {
      // Refine ETA/direction once velocity warm marker is set server-side
      const refined = await apiFetch<NearestRainResponse>("/api/nearest-rain", {
        query: { lat: latitude, lng: longitude, lang: locale.value },
        timeout: 16_000,
      });
      store.setResult(refined);
      writeStale(latitude, longitude, refined);
    }
  } catch {
    if (!stale) {
      store.reset();
      store.setError(t("errors.nearestRain"));
    } else {
      store.setLoading(false);
    }
  }
}
```

Do not loop: only one refine attempt. If refine fails, keep first card (wrap refine in inner try/catch).

```typescript
    if (data.motionPending) {
      try {
        const refined = await apiFetch<NearestRainResponse>("/api/nearest-rain", {
          query: { lat: latitude, lng: longitude, lang: locale.value },
          timeout: 16_000,
        });
        store.setResult(refined);
        writeStale(latitude, longitude, refined);
      } catch {
        // Keep fast card
      }
    }
```

- [ ] **Step 2: Manual sanity check (local if API up)**

Open app, cold load: card appears without waiting full motion; refine updates ETA when possible. Map tiles appear without ~10s blank.

- [ ] **Step 3: Commit**

```bash
git add apps/web/composables/useNearestRain.ts
git commit -m "fix: refresh nearest-rain once when motion is pending"
```

---

### Task 4: Verification sweep

**Files:**
- None required (run suite + fix fallout)

- [ ] **Step 1: Run API tests**

Run: `cd apps/api; python -m pytest -v`

Expected: PASS

- [ ] **Step 2: Spec checklist**

Confirm against `docs/superpowers/specs/2026-10-05-radar-nearest-rain-latency-design.md`:

- [ ] z≥6 fast tile without 9-frame block
- [ ] z<6 full clutter still awaited
- [ ] Short Cache-Control on fast tiles
- [ ] nearest-rain first cold skips motion + `motionPending`
- [ ] Second request builds motion / velocity cache
- [ ] FE single refine refresh
- [ ] location left alone

- [ ] **Step 3: Final commit only if fixes landed; otherwise done**

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| Fast tile z≥6, peek-only | Task 1 |
| Full path z<6 / when mask ready | Task 1 |
| Fast/full cache keys + Cache-Control | Task 1 |
| nearest-rain skip motion cold | Task 2 |
| Refine fills velocity (not stuck forever) | Task 2 warm marker + Task 3 FE |
| `motionPending` signal | Task 2 + 3 |
| location unchanged | Task 4 checklist |
| Targets ~3s / ~3–5s | Emergent from Task 1–2; verify manually |

No TBD placeholders. Warm-on-Vercel background discarded in favor of explicit second request (matches spec MVP).
