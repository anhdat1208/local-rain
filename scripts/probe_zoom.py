"""Compare RainViewer z7 vs z8 at Chanh Hung exact pixel."""
from __future__ import annotations

import asyncio
import io
import math

import httpx
from PIL import Image

from app.services.radar import RadarService
from app.services.radar_dbz import pixel_dbz
from app.utils.geo import haversine_m, tile_pixel_to_latlon


def sample_zoom(
    img: Image.Image,
    tile_x: int,
    tile_y: int,
    zoom: int,
    user_lat: float,
    user_lon: float,
    max_km: float = 8.0,
) -> list[tuple[float, float, float, float]]:
    hits = []
    w, h = img.size
    for py in range(0, h, 1):
        for px in range(0, w, 1):
            r, g, b, a = img.getpixel((px, py))
            dbz = pixel_dbz(r, g, b, a)
            if dbz < 25:
                continue
            lat, lon = tile_pixel_to_latlon(tile_x, tile_y, zoom, px + 0.5, py + 0.5, w)
            dist = haversine_m(user_lat, user_lon, lat, lon)
            if dist <= max_km * 1000:
                hits.append((dist, dbz, lat, lon))
    hits.sort(key=lambda x: (x[0], -x[1]))
    return hits


def tile_of(lat: float, lon: float, zoom: int) -> tuple[int, int, int, int]:
    n = 2**zoom
    xt = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    yt = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    tx, ty = int(xt), int(yt)
    px, py = int((xt - tx) * 256), int((yt - ty) * 256)
    return tx, ty, px, py


async def main() -> None:
    lat, lon = 10.745, 106.670
    radar = RadarService()
    frames = await radar.get_radar_frames()
    frame = frames.frames[-1]
    # get raw rainviewer template from radar service internals
    up = await radar.upstream_for_frame(frame.unix_time)
    print("frame", frame.timestamp)
    print("upstream", up)

    async with httpx.AsyncClient(timeout=30) as client:
        for zoom in (7, 8, 9):
            # rewrite zoom in URL if template has {z}
            tx, ty, px, py = tile_of(lat, lon, zoom)
            url = up.replace("{z}", str(zoom)).replace("{x}", str(tx)).replace("{y}", str(ty))
            # also try without color/analysis path fixes
            r = await client.get(url)
            print(f"\nz={zoom} tile={tx},{ty} px={px},{py} status={r.status_code} bytes={len(r.content)}")
            if r.status_code != 200:
                continue
            img = Image.open(io.BytesIO(r.content)).convert("RGBA")
            exact = pixel_dbz(*img.getpixel((px, py)))
            # 5x5 around exact
            neigh = []
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    xx = min(255, max(0, px + dx))
                    yy = min(255, max(0, py + dy))
                    neigh.append(pixel_dbz(*img.getpixel((xx, yy))))
            print(f"  exact_dbz={exact:.1f} max5={max(neigh):.1f} cnt25={sum(1 for v in neigh if v>=25)}")
            hits = sample_zoom(img, tx, ty, zoom, lat, lon, max_km=6)
            print(f"  hits<=6km >=25dBZ: {len(hits)}")
            for h in hits[:8]:
                print(f"    {h[0]:6.0f}m dbz={h[1]:5.1f} @ {h[2]:.5f},{h[3]:.5f}")


if __name__ == "__main__":
    asyncio.run(main())
