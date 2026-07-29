"""Check why nearest 2.7km hits fail DETECT support."""
from __future__ import annotations

import asyncio
import io
from collections import defaultdict

import httpx
from PIL import Image

from app.services.radar import RadarService
from app.services.radar_dbz import pixel_dbz
from app.utils.geo import haversine_m, latlon_to_tile, tile_pixel_to_latlon

RADAR_ZOOM = 7
DETECT_MIN_DBZ = 35.0
LOCAL_SOFT_DBZ = 30.0
PIXEL_STEP = 2
RADIUS = 4


async def main() -> None:
    lat0, lon0 = 10.745, 106.670
    radar = RadarService()
    frames = await radar.get_radar_frames()
    frame = frames.frames[-1]
    up = await radar.upstream_for_frame(frame.unix_time)
    tx, ty = latlon_to_tile(lat0, lon0, RADAR_ZOOM)
    url = up.replace("{z}", str(RADAR_ZOOM)).replace("{x}", str(tx)).replace("{y}", str(ty))
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(url)
        img = Image.open(io.BytesIO(r.content)).convert("RGBA")

    soft = []
    hard = []
    for py in range(0, 256, PIXEL_STEP):
        for px in range(0, 256, PIXEL_STEP):
            dbz = pixel_dbz(*img.getpixel((px, py)))
            if dbz < LOCAL_SOFT_DBZ:
                continue
            lat, lon = tile_pixel_to_latlon(tx, ty, RADAR_ZOOM, px + 0.5, py + 0.5, 256)
            dist = haversine_m(lat0, lon0, lat, lon)
            soft.append((px, py, dbz, dist, lat, lon))
            if dbz >= DETECT_MIN_DBZ:
                hard.append((px, py, dbz, dist, lat, lon))

    def support(pool, px, py):
        return sum(1 for ox, oy, *_ in pool if abs(ox - px) <= RADIUS and abs(oy - py) <= RADIUS)

    print(f"frame={frame.timestamp} soft={len(soft)} hard={len(hard)}")
    hard.sort(key=lambda x: x[3])
    print("\nNearest HARD pixels:")
    for item in hard[:12]:
        px, py, dbz, dist, lat, lon = item
        print(
            f"  {dist:6.0f}m dbz={dbz:5.1f} support={support(hard, px, py)} "
            f"@ {lat:.5f},{lon:.5f} px=({px},{py})"
        )

    soft_near = [s for s in soft if s[3] <= 4500]
    soft_near.sort(key=lambda x: x[3])
    print("\nSOFT within 4.5km:")
    for item in soft_near[:12]:
        px, py, dbz, dist, lat, lon = item
        print(
            f"  {dist:6.0f}m dbz={dbz:5.1f} support={support(soft, px, py)} "
            f"@ {lat:.5f},{lon:.5f}"
        )

    # score simulation
    CORE = 550.0
    BONUS = 4000.0
    NEAR_R = 3000.0

    def score(dist, dbz):
        strength = max(0.0, dbz - DETECT_MIN_DBZ)
        s = dist - CORE * strength
        if dist <= NEAR_R:
            s -= BONUS
        return s

    candidates = []
    for px, py, dbz, dist, lat, lon in hard:
        if support(hard, px, py) >= 4:
            candidates.append(("hard", dist, dbz, score(dist, dbz), lat, lon))
    for px, py, dbz, dist, lat, lon in soft:
        if dist <= 2000 and support(soft, px, py) >= 2:
            candidates.append(("soft", dist, dbz, score(dist, dbz), lat, lon))
    candidates.sort(key=lambda c: c[3])
    print("\nCurrent algorithm winners (lowest score):")
    for c in candidates[:8]:
        print(f"  {c}")


if __name__ == "__main__":
    asyncio.run(main())
