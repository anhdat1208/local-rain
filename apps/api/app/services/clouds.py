from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import re
from datetime import UTC, datetime, timedelta

from dataclasses import dataclass

from PIL import Image, ImageFilter

from app.core.config import get_settings
from app.core.redis import get_redis
from app.schemas.clouds import CloudsResponse

CACHE_KEY = "clouds:himawari:v19"
STALE_CACHE_KEY = "clouds:himawari:stale:v19"
CACHE_TTL_SECONDS = 180
STALE_CACHE_TTL_SECONDS = 2 * 60 * 60
TILE_CACHE_TTL_SECONDS = 300
TRANSPARENT_PNG: bytes | None = None

CAPABILITIES_URL = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/1.0.0/WMTSCapabilities.xml"
)

# Day: visible Band3 → cloud mask over colored Earth. Night: clean IR.
DAY_LAYER = "Himawari_AHI_Band3_Red_Visible_1km"
DAY_MATRIX = "GoogleMapsCompatible_Level7"
DAY_MAX_ZOOM = 7
NIGHT_LAYER = "Himawari_AHI_Band13_Clean_Infrared"
NIGHT_MATRIX = "GoogleMapsCompatible_Level6"
NIGHT_MAX_ZOOM = 6
VIETNAM_UTC_OFFSET_HOURS = 7

FRAME_INTERVAL_MINUTES = 10
FRAME_PROBE_STEPS = 14  # look back up to ~2h for the newest published scan
PROBE_LAT = 14.5
PROBE_LON = 108.5

# Fixed brightness-temperature calibration for the night IR channel. Deriving the
# threshold per tile made neighbouring tiles disagree at their shared edge and made
# the whole scene jump between refreshes, so the mapping is constant instead.
NIGHT_IR_FLOOR = 92  # warm surface and clear sky
NIGHT_IR_TOP = 215  # coldest convective tops
NIGHT_IR_GAMMA = 1.45  # holds low cloud down instead of flattening into gray fog
NIGHT_CLOUD_RGB = (247, 250, 253)


def _build_night_lut() -> list[int]:
    span = NIGHT_IR_TOP - NIGHT_IR_FLOOR
    lut: list[int] = []
    for value in range(256):
        if value <= NIGHT_IR_FLOOR:
            lut.append(0)
            continue
        ratio = min(1.0, (value - NIGHT_IR_FLOOR) / span)
        lut.append(round(255 * pow(ratio, NIGHT_IR_GAMMA)))
    return lut


NIGHT_ALPHA_LUT = _build_night_lut()

# Soft-tile alpha above this counts as cloud in the local sky sample
CLOUD_ALPHA_FLOOR = 40
CLOUDY_COVER = 0.32
PARTLY_COVER = 0.15


@dataclass(frozen=True, slots=True)
class CloudCoverSample:
    cover: float
    mode: str
    timestamp: str | None = None
    ok: bool = True


class CloudsService:
    async def get_clouds(self) -> CloudsResponse:
        cached = self._read_cache()
        if cached is not None:
            return cached

        # Stale-while-revalidate: serve previous meta immediately if present, refresh in background
        stale = self._read_stale_cache()
        if stale is not None:
            asyncio.create_task(self._safe_refresh_clouds_meta())
            return stale

        return await self._refresh_clouds_meta()

    async def _safe_refresh_clouds_meta(self) -> None:
        try:
            await self._refresh_clouds_meta()
        except Exception:
            return

    async def _refresh_clouds_meta(self) -> CloudsResponse:
        mode = self._local_mode()
        layer_id, matrix, max_zoom = (
            (DAY_LAYER, DAY_MATRIX, DAY_MAX_ZOOM)
            if mode == "day"
            else (NIGHT_LAYER, NIGHT_MATRIX, NIGHT_MAX_ZOOM)
        )
        timestamp = await self._resolve_timestamp(layer_id, matrix, max_zoom)
        upstream_template = (
            "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
            f"{layer_id}/default/{timestamp}/{matrix}/{{z}}/{{y}}/{{x}}.png"
        )
        public_base = get_settings().resolved_public_api_base
        # Cache-bust query so browsers / SW don't keep an older soft-tile recipe
        tile_url_template = f"{public_base}/api/clouds/tiles/{{z}}/{{x}}/{{y}}.png?v=19"
        response = CloudsResponse(
            tile_url_template=tile_url_template,
            timestamp=timestamp,
            source=layer_id.lower().replace("_", "-"),
            mode=mode,
            max_zoom=max_zoom,
            attribution="NASA GIBS / JMA Himawari",
        )
        self._write_cache(response, upstream_template)
        return response

    async def sample_cover(self, latitude: float, longitude: float) -> CloudCoverSample:
        """Estimate cloud fraction over a ~10 km window from the soft Himawari tile."""
        try:
            meta = self._read_cache_meta()
            if meta is None:
                # Don't block nearest-rain on a full GIBS probe — warm meta in background
                asyncio.create_task(self._safe_refresh_clouds_meta())
                return CloudCoverSample(cover=0.0, mode=self._local_mode(), ok=False)

            mode = str(meta.get("mode") or self._local_mode())
            timestamp = meta.get("timestamp")
            max_zoom = DAY_MAX_ZOOM if mode == "day" else NIGHT_MAX_ZOOM
            tile_x, tile_y, px, py = self._latlon_to_pixel(latitude, longitude, max_zoom)
            soft = await self.get_soft_tile(max_zoom, tile_x, tile_y)
            image = Image.open(io.BytesIO(soft)).convert("RGBA")
            cover = self._alpha_cover(image, px, py, radius=5)
            return CloudCoverSample(
                cover=cover,
                mode=mode,
                timestamp=str(timestamp) if timestamp else None,
                ok=True,
            )
        except Exception:
            return CloudCoverSample(cover=0.0, mode=self._local_mode(), ok=False)

    def _latlon_to_pixel(
        self, lat: float, lon: float, zoom: int
    ) -> tuple[int, int, int, int]:
        scale = 2**zoom
        lat_rad = math.radians(lat)
        xt = (lon + 180.0) / 360.0 * scale
        yt = (
            (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
            / 2.0
            * scale
        )
        tile_x = int(xt)
        tile_y = int(yt)
        tile_x = max(0, min(scale - 1, tile_x))
        tile_y = max(0, min(scale - 1, tile_y))
        px = int((xt - tile_x) * 256)
        py = int((yt - tile_y) * 256)
        return tile_x, tile_y, max(0, min(255, px)), max(0, min(255, py))

    def _alpha_cover(self, image: Image.Image, px: int, py: int, radius: int) -> float:
        pixels = image.load()
        width, height = image.size
        cloudy = 0
        total = 0
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                xx = min(width - 1, max(0, px + dx))
                yy = min(height - 1, max(0, py + dy))
                alpha = pixels[xx, yy][3]
                total += 1
                if alpha >= CLOUD_ALPHA_FLOOR:
                    cloudy += 1
        if total <= 0:
            return 0.0
        return cloudy / float(total)

    async def get_soft_tile(self, z: int, x: int, y: int) -> bytes:
        meta = self._read_cache_meta()
        if meta is None:
            # Warm metadata then retry once.
            await self.get_clouds()
            meta = self._read_cache_meta()
        if meta is None:
            raise RuntimeError("Cloud imagery metadata unavailable")

        cache_key = f"clouds:tile:v19:{meta['mode']}:{meta['timestamp']}:{z}:{x}:{y}"
        try:
            cached = get_redis().get(cache_key)
            if cached:
                return base64.b64decode(cached)
        except Exception:
            pass

        upstream = (
            meta["upstream"]
            .replace("{z}", str(z))
            .replace("{x}", str(x))
            .replace("{y}", str(y))
        )
        raw = await self._fetch_upstream_bytes(upstream, meta)
        if raw is None:
            return self._transparent_tile()

        soft = self._soften_tile(raw, meta["mode"])
        try:
            get_redis().setex(
                cache_key,
                TILE_CACHE_TTL_SECONDS,
                base64.b64encode(soft).decode("ascii"),
            )
        except Exception:
            pass
        return soft

    async def _fetch_upstream_bytes(self, upstream: str, meta: dict) -> bytes | None:
        """Fetch one GIBS tile, retrying the same URL rather than another frame.

        GIBS intermittently answers 404 for tiles that do exist — the same request
        succeeds moments later. Treating that as missing data and reaching for a
        neighbouring timestamp stitches two different weather scenes into one image
        and leaves hard rectangular seams, so the timestamp never changes here.
        """
        from app.core.http_client import get_http_client

        return await self._get_tile_bytes(get_http_client(), upstream, attempts=4)

    async def _get_tile_bytes(
        self, client: httpx.AsyncClient, url: str, attempts: int
    ) -> bytes | None:
        for attempt in range(attempts):
            try:
                response = await client.get(url)
                if response.status_code == 200 and response.content:
                    return response.content
            except Exception:
                pass
            if attempt < attempts - 1:
                await asyncio.sleep(0.15 * (attempt + 1))
        return None

    def _transparent_tile(self) -> bytes:
        global TRANSPARENT_PNG
        if TRANSPARENT_PNG is None:
            image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
            out = io.BytesIO()
            image.save(out, format="PNG")
            TRANSPARENT_PNG = out.getvalue()
        return TRANSPARENT_PNG

    def _soften_tile(self, raw: bytes, mode: str) -> bytes:
        image = Image.open(io.BytesIO(raw))
        if mode == "day":
            # Extract brighter cloud tops only. Midday Band3 over VN often has
            # land/sea mean ~100+; a low floor paints the whole tile milky white.
            gray = image.convert("L")
            gray = gray.filter(ImageFilter.GaussianBlur(radius=0.2))
            gray = gray.filter(ImageFilter.UnsharpMask(radius=1.0, percent=125, threshold=2))
            sample = list(gray.getdata())
            sample.sort()
            # Keep roughly the brightest ~38% as candidate cloud, with a safer floor.
            percentile_floor = sample[int(len(sample) * 0.62)]
            floor = max(62, min(126, int(percentile_floor)))
            span = max(38, 198 - floor)
            alpha_lut = [
                0 if i < floor else min(255, int((i - floor) / span * 255)) for i in range(256)
            ]
            alpha = gray.point(alpha_lut)
            # Guardrail: if mask is almost fully transparent, relax threshold.
            hist = alpha.histogram()
            visible_ratio = sum(hist[1:]) / float(len(sample) or 1)
            if visible_ratio < 0.02:
                relaxed_floor = max(36, min(104, floor - 24))
                relaxed_span = max(32, 182 - relaxed_floor)
                relaxed_lut = [
                    0
                    if i < relaxed_floor
                    else min(235, int((i - relaxed_floor) / relaxed_span * 235))
                    for i in range(256)
                ]
                alpha = gray.point(relaxed_lut)
            # Soft cool-white cloud body.
            lift = gray.point(lambda v: min(255, 178 + int(max(0, v - floor) * 1.3)))
            red = lift
            green = lift.point(lambda v: min(255, v + 2))
            blue = lift.point(lambda v: min(255, v + 8))
            image = Image.merge("RGBA", (red, green, blue, alpha))
        else:
            # Night IR: one continuous grey ramp, cloud depth carried by alpha so the
            # tile composites straight onto the black field the client draws below it.
            gray = image.convert("L").filter(ImageFilter.GaussianBlur(radius=0.9))
            alpha = gray.point(NIGHT_ALPHA_LUT)
            size = gray.size
            channels = [Image.new("L", size, level) for level in NIGHT_CLOUD_RGB]
            image = Image.merge("RGBA", (*channels, alpha))

        out = io.BytesIO()
        image.save(out, format="PNG", compress_level=3)
        return out.getvalue()

    def _local_mode(self) -> str:
        local_now = datetime.now(tz=UTC) + timedelta(hours=VIETNAM_UTC_OFFSET_HOURS)
        return "day" if 6 <= local_now.hour < 18 else "night"

    async def _resolve_timestamp(self, layer_id: str, matrix: str, max_zoom: int) -> str:
        probed = await self._probe_latest_frame(layer_id, matrix, max_zoom)
        if probed is not None:
            return probed

        try:
            from app.core.http_client import get_http_client

            response = await get_http_client().get(CAPABILITIES_URL, timeout=20.0)
            response.raise_for_status()
            xml = response.text
        except Exception:
            return self._fallback_timestamp()

        parsed = self._parse_default_time(xml, layer_id)
        return parsed or self._fallback_timestamp()

    async def _probe_latest_frame(
        self, layer_id: str, matrix: str, max_zoom: int
    ) -> str | None:
        """Find the newest published frame by asking for one tile over Vietnam.

        The capabilities document advertises a Default that regularly trails the
        real archive by a couple of hours, and scan slots are irregular, so the
        only reliable answer comes from the tile endpoint itself.
        """
        tile_x, tile_y = self._reference_tile(max_zoom)
        now = datetime.now(tz=UTC)
        newest = now.replace(
            minute=(now.minute // FRAME_INTERVAL_MINUTES) * FRAME_INTERVAL_MINUTES,
            second=0,
            microsecond=0,
        )
        candidates = [
            (newest - timedelta(minutes=FRAME_INTERVAL_MINUTES * step)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            for step in range(FRAME_PROBE_STEPS)
        ]

        # Probe newest-first in small parallel batches — same correctness as sequential
        # (we still pick the newest success) but much faster on cold start.
        from app.core.http_client import get_http_client

        client = get_http_client()
        batch_size = 4
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start : start + batch_size]

            async def probe_one(stamp: str) -> str | None:
                url = (
                    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
                    f"{layer_id}/default/{stamp}/{matrix}/{max_zoom}/{tile_y}/{tile_x}.png"
                )
                if await self._get_tile_bytes(client, url, attempts=2) is not None:
                    return stamp
                return None

            results = await asyncio.gather(*(probe_one(stamp) for stamp in batch))
            for stamp, hit in zip(batch, results, strict=True):
                if hit is not None:
                    return stamp
        return None

    def _reference_tile(self, zoom: int) -> tuple[int, int]:
        scale = 2**zoom
        lat_rad = math.radians(PROBE_LAT)
        x = int((PROBE_LON + 180.0) / 360.0 * scale)
        y = int(
            (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi)
            / 2.0
            * scale
        )
        return max(0, min(scale - 1, x)), max(0, min(scale - 1, y))

    def _parse_default_time(self, xml: str, layer_id: str) -> str | None:
        marker = f"<ows:Identifier>{layer_id}</ows:Identifier>"
        start = xml.find(marker)
        if start < 0:
            return None
        end = xml.find("</Layer>", start)
        block = xml[start:end] if end > start else xml[start : start + 40_000]

        for default_match in re.finditer(r"<Default>([^<]+)</Default>", block):
            value = default_match.group(1).strip()
            if "T" in value and value.endswith("Z"):
                return value

        ranges = re.findall(r"<Value>([^<]+)</Value>", block)
        latest: datetime | None = None
        for item in ranges:
            parts = item.split("/")
            if len(parts) >= 2 and "T" in parts[1]:
                try:
                    candidate = datetime.fromisoformat(parts[1].replace("Z", "+00:00"))
                except ValueError:
                    continue
                if latest is None or candidate > latest:
                    latest = candidate
        if latest is None:
            return None
        return latest.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _fallback_timestamp(self) -> str:
        now = datetime.now(tz=UTC) - timedelta(minutes=50)
        minute = (now.minute // 10) * 10
        stamped = now.replace(minute=minute, second=0, microsecond=0)
        return stamped.strftime("%Y-%m-%dT%H:%M:%SZ")

    def _read_cache(self) -> CloudsResponse | None:
        meta = self._read_cache_meta()
        if meta is None:
            return None
        try:
            return CloudsResponse.model_validate(meta["response"])
        except Exception:
            return None

    def _read_stale_cache(self) -> CloudsResponse | None:
        try:
            raw = get_redis().get(STALE_CACHE_KEY)
        except Exception:
            return None
        if not raw:
            return None
        try:
            meta = json.loads(raw)
            return CloudsResponse.model_validate(meta["response"])
        except Exception:
            return None

    def _read_cache_meta(self) -> dict | None:
        try:
            raw = get_redis().get(CACHE_KEY)
        except Exception:
            return None
        if not raw:
            # Fall back to stale meta so soft tiles / sample_cover still work during refresh
            try:
                raw = get_redis().get(STALE_CACHE_KEY)
            except Exception:
                return None
            if not raw:
                return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def _write_cache(self, payload: CloudsResponse, upstream_template: str) -> None:
        blob = json.dumps(
            {
                "response": payload.model_dump(by_alias=True),
                "upstream": upstream_template,
                "mode": payload.mode,
                "timestamp": payload.timestamp,
            }
        )
        try:
            redis = get_redis()
            redis.setex(CACHE_KEY, CACHE_TTL_SECONDS, blob)
            redis.setex(STALE_CACHE_KEY, STALE_CACHE_TTL_SECONDS, blob)
        except Exception:
            return


def get_clouds_service() -> CloudsService:
    return CloudsService()
