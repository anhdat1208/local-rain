"""Sample radar dBZ around Chanh Hung / related spots."""
from __future__ import annotations

import asyncio
import io
import math

import httpx
from PIL import Image

from app.services.radar import RadarService
from app.services.radar_dbz import pixel_dbz

RADAR_ZOOM = 7
TILE_SIZE = 256

SPOTS = [
    ("default_HCMC", 10.7626, 106.6602),
    ("ChanhHung_est", 10.7450, 106.6700),
    ("ChanhHung_S", 10.7400, 106.6750),
    ("ChanhHung_N", 10.7500, 106.6650),
    ("AnDuongVuong", 10.7550, 106.6650),
    ("TaoDan_est", 10.7720, 106.6920),
    ("prev_cell", 10.78474, 106.63879),
]


def tile_xy(lat: float, lon: float) -> tuple[int, int, int, int]:
    n = 2**RADAR_ZOOM
    lat_rad = math.radians(lat)
    xt = (lon + 180.0) / 360.0 * n
    yt = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    tile_x = int(xt)
    tile_y = int(yt)
    px = int((xt - tile_x) * TILE_SIZE)
    py = int((yt - tile_y) * TILE_SIZE)
    return tile_x, tile_y, px, py


async def sample(
    client: httpx.AsyncClient, tile_url: str, lat: float, lon: float, radius: int = 6
) -> dict:
    tile_x, tile_y, px, py = tile_xy(lat, lon)
    url = (
        tile_url.replace("{z}", str(RADAR_ZOOM))
        .replace("{x}", str(tile_x))
        .replace("{y}", str(tile_y))
    )
    r = await client.get(url)
    r.raise_for_status()
    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    samples: list[float] = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            xx = max(0, min(TILE_SIZE - 1, px + dx))
            yy = max(0, min(TILE_SIZE - 1, py + dy))
            r, g, b, a = img.getpixel((xx, yy))
            d = pixel_dbz(r, g, b, a)
            if d > 0:
                samples.append(d)
    return {
        "max": max(samples) if samples else None,
        "n": len(samples),
        "n25": sum(1 for d in samples if d >= 25),
        "n30": sum(1 for d in samples if d >= 30),
        "n35": sum(1 for d in samples if d >= 35),
        "n40": sum(1 for d in samples if d >= 40),
        "tile": f"{tile_x},{tile_y}",
        "px": f"{px},{py}",
    }


async def main() -> None:
    radar = RadarService()
    frames = await radar.get_radar_frames()
    print(f"frames={len(frames.frames)} latest={frames.frames[-1].timestamp}")
    # check last 3 frames
    for frame in frames.frames[-3:]:
        up = await radar.upstream_for_frame(frame.unix_time)
        print(f"\n=== frame {frame.timestamp} ===")
        async with httpx.AsyncClient(timeout=20) as client:
            for name, lat, lon in SPOTS:
                s = await sample(client, up, lat, lon)
                print(
                    f"{name:16} max={s['max']!s:>6} n={s['n']:3} "
                    f">=25={s['n25']:2} >=30={s['n30']:2} >=35={s['n35']:2} "
                    f">=40={s['n40']:2} tile={s['tile']} px={s['px']}"
                )


if __name__ == "__main__":
    asyncio.run(main())
