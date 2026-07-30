"""Report cluster size behind each nearest-rain hit (speckle vs real cell)."""
from __future__ import annotations

import asyncio
import io

import httpx
from PIL import Image

from app.services.radar import RadarService
from app.services.radar_dbz import pixel_dbz
from app.utils.geo import haversine_m, latlon_to_tile, tile_pixel_to_latlon

RADAR_ZOOM = 7
SPOTS = {
    "ChanhHung_user": (10.745, 106.670),
    "box_cholon": (10.753, 106.645),
    "box_binhhung": (10.723, 106.678),
}


async def main() -> None:
    radar = RadarService()
    frames = await radar.get_radar_frames()
    frame = frames.frames[-1]
    up = await radar.upstream_for_frame(frame.unix_time)
    print(f"frame={frame.timestamp}")

    async with httpx.AsyncClient(timeout=30) as client:
        for name, (lat, lon) in SPOTS.items():
            tx, ty = latlon_to_tile(lat, lon, RADAR_ZOOM)
            url = up.replace("{z}", str(RADAR_ZOOM)).replace("{x}", str(tx)).replace("{y}", str(ty))
            r = await client.get(url)
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")

            grid = {}
            for py in range(256):
                for px in range(256):
                    d = pixel_dbz(*img.getpixel((px, py)))
                    if d > 0:
                        grid[(px, py)] = d

            # find strongest pixel within 8 km and measure its contiguous cluster
            best = None
            for (px, py), d in grid.items():
                la, lo = tile_pixel_to_latlon(tx, ty, RADAR_ZOOM, px + 0.5, py + 0.5, 256)
                dist = haversine_m(lat, lon, la, lo)
                if dist > 8000:
                    continue
                if best is None or (d, -dist) > (best[2], -best[3]):
                    best = (px, py, d, dist)

            if best is None:
                print(f"\n{name}: no echo within 8 km")
                continue

            px, py, d, dist = best
            # flood fill contiguous pixels >= 25 dBZ
            seen = set()
            stack = [(px, py)]
            peak = 0.0
            while stack:
                cur = stack.pop()
                if cur in seen or cur not in grid or grid[cur] < 25:
                    continue
                seen.add(cur)
                peak = max(peak, grid[cur])
                cx, cy = cur
                for nb in ((cx+1, cy), (cx-1, cy), (cx, cy+1), (cx, cy-1)):
                    if nb not in seen:
                        stack.append(nb)
            strong = sum(1 for c in seen if grid[c] >= 35)
            print(
                f"\n{name}: strongest {d:.0f} dBZ at {dist:.0f} m | "
                f"cluster px={len(seen)} peak={peak:.0f} dBZ px>=35={strong}"
            )
            km2 = len(seen) * 1.2 * 1.2
            print(f"  approx cluster area ~{km2:.0f} km^2 (1 px ≈ 1.2 km at z7)")


if __name__ == "__main__":
    asyncio.run(main())
