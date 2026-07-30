"""Probe dBZ exactly at Nguyen Van Linh / QL50 (Binh Hung)."""
from __future__ import annotations

import asyncio
import io
import math

import httpx
from PIL import Image

from app.services.radar import RadarService
from app.services.radar_dbz import MAP_MIN_DBZ, pixel_dbz
from app.utils.geo import haversine_m, latlon_to_tile, tile_pixel_to_latlon

# Camera: Nguyen Van Linh x QL50
SPOT = (10.725, 106.685)
RADAR_ZOOM = 7


async def main() -> None:
    radar = RadarService()
    frames = await radar.get_radar_frames()
    frame = frames.frames[-1]
    up = await radar.upstream_for_frame(frame.unix_time)
    print(f"frame={frame.timestamp} MAP_MIN_DBZ={MAP_MIN_DBZ}")

    tx, ty = latlon_to_tile(SPOT[0], SPOT[1], RADAR_ZOOM)
    url = up.replace("{z}", str(RADAR_ZOOM)).replace("{x}", str(tx)).replace("{y}", str(ty))
    async with httpx.AsyncClient(timeout=25) as client:
        r = await client.get(url)
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")

    n = 2**RADAR_ZOOM
    xt = (SPOT[1] + 180.0) / 360.0 * n
    lat_rad = math.radians(SPOT[0])
    yt = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    px, py = int((xt - tx) * 256), int((yt - ty) * 256)
    exact = pixel_dbz(*img.getpixel((px, py)))
    print(f"exact pixel={px},{py} dbz={exact:.1f}")

    hits = []
    for yy in range(0, 256, 1):
        for xx in range(0, 256, 1):
            d = pixel_dbz(*img.getpixel((xx, yy)))
            if d < 20:
                continue
            la, lo = tile_pixel_to_latlon(tx, ty, RADAR_ZOOM, xx + 0.5, yy + 0.5, 256)
            dist = haversine_m(SPOT[0], SPOT[1], la, lo)
            if dist <= 8_000:
                hits.append((dist, d, la, lo))
    hits.sort(key=lambda h: (h[0], -h[1]))
    print(f"hits<=8km >=20: {len(hits)}")
    for thr in (20, 25, 30, 35, 40):
        near = [h for h in hits if h[1] >= thr]
        if near:
            print(f"  nearest>={thr}: {near[0][0]:.0f}m dbz={near[0][1]:.0f}")
        else:
            print(f"  nearest>={thr}: none")
    print("top10:")
    for h in hits[:10]:
        print(f"  {h[0]:6.0f}m {h[1]:5.1f} dBZ")


if __name__ == "__main__":
    asyncio.run(main())
