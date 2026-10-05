from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import UTC, datetime
from typing import Any

from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.core.redis import get_redis
from app.schemas.radar import RadarFrameSchema, RadarResponse
from app.services.clutter_mask import CLUTTER_MIN_ZOOM, clutter_mask, peek_clutter_mask
from app.services.radar_dbz import filter_tile_below_dbz

RAINVIEWER_MAPS_URL = "https://api.rainviewer.com/public/weather-maps.json"
CACHE_KEY = "radar:frames:v2"
UPSTREAM_CACHE_KEY = "radar:upstreams:v2"
STALE_CACHE_KEY = "radar:frames:stale:v1"
STALE_UPSTREAM_CACHE_KEY = "radar:upstreams:stale:v1"
CACHE_TTL_SECONDS = 180
TILE_CACHE_TTL_SECONDS = 180
# A filtered tile is keyed by frame and clutter generation, so its bytes never change —
# no reason to re-filter it every 3 minutes.
FILTERED_TILE_TTL_SECONDS = 900
FAST_FILTERED_TILE_TTL_SECONDS = 60
FAST_TILE_CACHE_PREFIX = "radar:tile:fast:v1"
FAST_CACHE_CONTROL = "public, max-age=45"
FULL_CACHE_CONTROL = "public, max-age=120"
STALE_CACHE_TTL_SECONDS = 2 * 60 * 60
# Unsmoothed tiles — same as nearest-rain scan (sharp cores, less soft fringe)
UPSTREAM_OPTIONS = "2/0_1.png"

_frames_inflight: asyncio.Task[RadarResponse] | None = None


class RadarService:
    async def get_radar_frames(self) -> RadarResponse:
        global _frames_inflight
        cached = self._read_cache()
        if cached is not None:
            return cached

        # Serve stale frames immediately while RainViewer refresh runs in the background
        stale = self._read_stale_cache()
        if stale is not None and stale.frames:
            asyncio.create_task(self._safe_refresh_frames())
            return stale

        if _frames_inflight is not None:
            return await _frames_inflight

        async def run() -> RadarResponse:
            global _frames_inflight
            try:
                payload = await self._fetch_rainviewer()
                response, upstreams = self._to_response(payload)
                if not response.frames:
                    stale_inner = self._read_stale_cache()
                    if stale_inner is not None:
                        return stale_inner
                self._write_cache(response, upstreams)
                return response
            finally:
                _frames_inflight = None

        _frames_inflight = asyncio.create_task(run())
        return await _frames_inflight

    async def _safe_refresh_frames(self) -> None:
        try:
            payload = await self._fetch_rainviewer()
            response, upstreams = self._to_response(payload)
            if response.frames:
                self._write_cache(response, upstreams)
        except Exception:
            return

    async def upstream_for_frame(self, unix_time: int) -> str:
        upstreams = self._read_upstreams()
        template = upstreams.get(str(unix_time))
        if template:
            return template
        stale_upstreams = self._read_stale_upstreams()
        template = stale_upstreams.get(str(unix_time))
        if template:
            return template
        await self.get_radar_frames()
        upstreams = self._read_upstreams()
        template = upstreams.get(str(unix_time))
        if not template:
            stale_upstreams = self._read_stale_upstreams()
            template = stale_upstreams.get(str(unix_time))
        if not template:
            raise RuntimeError(f"No upstream radar tile for frame {unix_time}")
        return template

    def upstream_map(self) -> dict[int, str]:
        raw = self._read_upstreams() or self._read_stale_upstreams()
        out: dict[int, str] = {}
        for key, template in raw.items():
            try:
                out[int(key)] = template
            except (TypeError, ValueError):
                continue
        return out

    def newest_past_unix(self, upstreams: dict[int, str] | None = None) -> int | None:
        """Latest frame that has actually happened; nowcast frames are extrapolations."""
        times = (upstreams if upstreams is not None else self.upstream_map()).keys()
        now = int(time.time())
        past = [unix_time for unix_time in times if unix_time <= now]
        return max(past) if past else None

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

    async def _fetch_rainviewer(self) -> dict[str, Any]:
        response = await get_http_client().get(RAINVIEWER_MAPS_URL, timeout=8.0)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Unexpected RainViewer payload")
        return data

    def _to_response(
        self, payload: dict[str, Any]
    ) -> tuple[RadarResponse, dict[str, str]]:
        host = str(payload.get("host") or "https://tilecache.rainviewer.com").rstrip("/")
        radar = payload.get("radar") or {}
        past = radar.get("past") or []
        nowcast = radar.get("nowcast") or []
        public_base = get_settings().resolved_public_api_base

        frames: list[RadarFrameSchema] = []
        upstreams: dict[str, str] = {}
        for item in [*past, *nowcast]:
            if not isinstance(item, dict):
                continue
            unix_time = item.get("time")
            path = item.get("path")
            if not isinstance(unix_time, int) or not isinstance(path, str):
                continue
            upstream = f"{host}{path}/256/{{z}}/{{x}}/{{y}}/{UPSTREAM_OPTIONS}"
            upstreams[str(unix_time)] = upstream
            tile_url_template = (
                f"{public_base}/api/radar/tiles/{unix_time}/{{z}}/{{x}}/{{y}}.png"
            )
            frames.append(
                RadarFrameSchema(
                    timestamp=datetime.fromtimestamp(unix_time, tz=UTC).isoformat(),
                    unix_time=unix_time,
                    tile_url_template=tile_url_template,
                )
            )

        frames.sort(key=lambda frame: frame.unix_time)
        generated = payload.get("generated")
        if isinstance(generated, int):
            generated_at = datetime.fromtimestamp(generated, tz=UTC).isoformat()
        else:
            generated_at = datetime.now(tz=UTC).isoformat()

        return (
            RadarResponse(frames=frames, generated_at=generated_at, host=host),
            upstreams,
        )

    def _read_cache(self) -> RadarResponse | None:
        try:
            raw = get_redis().get(CACHE_KEY)
        except Exception:
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return RadarResponse.model_validate(data)
        except Exception:
            return None

    def _read_upstreams(self) -> dict[str, str]:
        try:
            raw = get_redis().get(UPSTREAM_CACHE_KEY)
        except Exception:
            return {}
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            return {}
        return {}

    def _read_stale_cache(self) -> RadarResponse | None:
        try:
            raw = get_redis().get(STALE_CACHE_KEY)
        except Exception:
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return RadarResponse.model_validate(data)
        except Exception:
            return None

    def _read_stale_upstreams(self) -> dict[str, str]:
        try:
            raw = get_redis().get(STALE_UPSTREAM_CACHE_KEY)
        except Exception:
            return {}
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except Exception:
            return {}
        return {}

    def _write_cache(self, response: RadarResponse, upstreams: dict[str, str]) -> None:
        try:
            redis = get_redis()
            redis.setex(CACHE_KEY, CACHE_TTL_SECONDS, response.model_dump_json(by_alias=True))
            redis.setex(UPSTREAM_CACHE_KEY, CACHE_TTL_SECONDS, json.dumps(upstreams))
            if response.frames:
                redis.setex(
                    STALE_CACHE_KEY,
                    STALE_CACHE_TTL_SECONDS,
                    response.model_dump_json(by_alias=True),
                )
                redis.setex(
                    STALE_UPSTREAM_CACHE_KEY,
                    STALE_CACHE_TTL_SECONDS,
                    json.dumps(upstreams),
                )
        except Exception:
            return


def get_radar_service() -> RadarService:
    return RadarService()
