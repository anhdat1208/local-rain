"""Sample current dBZ around Chanh Hung including weak rain."""
from __future__ import annotations

import asyncio
import io
import math

import httpx
from PIL import Image

from app.services.radar import RadarService
from app.services.radar_dbz import pixel_dbz
from app.utils.geo import haversine_m, latlon_to_tile, tile_pixel_to_latlon

RADAR_ZOOM = 7
LAT, LON = 10.745, 106.670


async def main() -> None:
    radar = RadarService()
    frames = await radar.get_radar_frames()
    print("latest frames:")
    for f in frames.frames[-4:]:
        print(" ", f.timestamp, f.unix_time)

    async with httpx.AsyncClient(timeout=25) as client:
        for frame in frames.frames[-3:]:
            up = await radar.upstream_for_frame(frame.unix_time)
            tx, ty = latlon_to_tile(LAT, LON, RADAR_ZOOM)
            url = up.replace("{z}", str(RADAR_ZOOM)).replace("{x}", str(tx)).replace("{y}", str(ty))
            r = await client.get(url)
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            # exact + neighbourhood
            n = 2**RADAR_ZOOM
            xt = (LON + 180.0) / 360.0 * n
            lat_rad = math.radians(LAT)
            yt = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
            px, py = int((xt - tx) * 256), int((yt - ty) * 256)
            exact = pixel_dbz(*img.getpixel((px, py)))
            hits = []
            for yy in range(0, 256, 1):
                for xx in range(0, 256, 1):
                    d = pixel_dbz(*img.getpixel((xx, yy)))
                    if d < 20:
                        continue
                    la, lo = tile_pixel_to_latlon(tx, ty, RADAR_ZOOM, xx + 0.5, yy + 0.5, 256)
                    dist = haversine_m(LAT, LON, la, lo)
                    if dist <= 15000:
                        hits.append((dist, d, la, lo))
            hits.sort(key=lambda h: (h[0], -h[1]))
            print(f"\n=== {frame.timestamp} exact={exact:.1f} hits<=15km>={20}dBZ={len(hits)} ===")
            for thr in (20, 25, 30, 35):
                near = [h for h in hits if h[1] >= thr]
                if near:
                    print(f"  nearest>={thr}: {near[0][0]:.0f}m dbz={near[0][1]:.1f}")
                else:
                    print(f"  nearest>={thr}: none")
            print("  top12:")
            for h in hits[:12]:
                print(f"    {h[0]:6.0f}m dbz={h[1]:5.1f}")


if __name__ == "__main__":
    asyncio.run(main())
