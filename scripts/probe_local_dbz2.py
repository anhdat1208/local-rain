"""Probe exact + neighbourhood dBZ at fine steps around Chanh Hung."""
from __future__ import annotations

import asyncio
import io
import math

import httpx
from PIL import Image

from app.services.radar import RadarService
from app.services.radar_dbz import pixel_dbz
from app.utils.geo import haversine_m, tile_pixel_to_latlon

RADAR_ZOOM = 7
TILE_SIZE = 256

# denser guess grid around Chanh Hung
CENTER = (10.745, 106.670)
OFFSETS_KM = [
    (0.0, 0.0),
    (0.5, 0.0),
    (-0.5, 0.0),
    (0.0, 0.5),
    (0.0, -0.5),
    (1.0, 0.0),
    (-1.0, 0.0),
    (0.0, 1.0),
    (0.0, -1.0),
    (1.5, 1.0),
    (-1.5, 1.0),
]


def latlon_to_frac(lat: float, lon: float) -> tuple[float, float]:
    n = 2**RADAR_ZOOM
    lat_rad = math.radians(lat)
    xt = (lon + 180.0) / 360.0 * n
    yt = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    return xt, yt


async def fetch_tile(client: httpx.AsyncClient, tile_url: str, tx: int, ty: int) -> Image.Image:
    url = (
        tile_url.replace("{z}", str(RADAR_ZOOM))
        .replace("{x}", str(tx))
        .replace("{y}", str(ty))
    )
    r = await client.get(url)
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content)).convert("RGBA")


def dbz_at(img: Image.Image, px: int, py: int) -> float:
    r, g, b, a = img.getpixel((px, py))
    return pixel_dbz(r, g, b, a)


async def main() -> None:
    radar = RadarService()
    frames = await radar.get_radar_frames()
    frame = frames.frames[-1]
    up = await radar.upstream_for_frame(frame.unix_time)
    print(f"frame={frame.timestamp}")

    async with httpx.AsyncClient(timeout=20) as client:
        cache: dict[tuple[int, int], Image.Image] = {}

        print("\n=== point samples ===")
        for dlat_km, dlon_km in OFFSETS_KM:
            lat = CENTER[0] + dlat_km / 111.0
            lon = CENTER[1] + dlon_km / (111.0 * math.cos(math.radians(CENTER[0])))
            xt, yt = latlon_to_frac(lat, lon)
            tx, ty = int(xt), int(yt)
            px, py = int((xt - tx) * TILE_SIZE), int((yt - ty) * TILE_SIZE)
            key = (tx, ty)
            if key not in cache:
                cache[key] = await fetch_tile(client, up, tx, ty)
            d = dbz_at(cache[key], px, py)
            # also 3x3 mean of neighbours (exact pixels)
            neigh = []
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    xx = min(TILE_SIZE - 1, max(0, px + dx))
                    yy = min(TILE_SIZE - 1, max(0, py + dy))
                    neigh.append(dbz_at(cache[key], xx, yy))
            print(
                f"dlat={dlat_km:+.1f} dlon={dlon_km:+.1f} "
                f"lat={lat:.5f} lon={lon:.5f} px=({px},{py}) "
                f"dbz={d:.1f} max3={max(neigh):.1f} cnt30={sum(1 for v in neigh if v>=30)}"
            )

        # full scan of tile 101,60: find all pixels >=30 and nearest to center
        print("\n=== nearest rain pixels on tile to center ===")
        img = await fetch_tile(client, up, 101, 60)
        hits = []
        for py in range(0, TILE_SIZE, 1):
            for px in range(0, TILE_SIZE, 1):
                d = dbz_at(img, px, py)
                if d < 25:
                    continue
                lat, lon = tile_pixel_to_latlon(101, 60, px, py, RADAR_ZOOM)
                dist = haversine_m(CENTER[0], CENTER[1], lat, lon)
                hits.append((dist, d, px, py, lat, lon))
        hits.sort(key=lambda h: (h[0], -h[1]))
        print(f"pixels>=25: {len(hits)}")
        for h in hits[:15]:
            dist, d, px, py, lat, lon = h
            print(f"  {dist:7.0f}m dbz={d:5.1f} px=({px},{py}) {lat:.5f},{lon:.5f}")

        # also call find_nearest for center
        from app.services.nearest_rain import NearestRainService

        svc = NearestRainService(radar)
        resp = await svc.find_nearest(CENTER[0], CENTER[1], "vi")
        print("\n=== find_nearest ===")
        print(resp.model_dump(by_alias=True))


if __name__ == "__main__":
    asyncio.run(main())
