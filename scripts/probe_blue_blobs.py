"""Histogram of radar dBZ on HCMC tile — see if blue blobs are weak noise."""
from __future__ import annotations

import asyncio
import io
from collections import Counter

import httpx
from PIL import Image

from app.services.radar import RadarService
from app.services.radar_dbz import MIN_DBZ, pixel_dbz
from app.utils.geo import haversine_m, latlon_to_tile, tile_pixel_to_latlon

RADAR_ZOOM = 7
# Chanh Hung
USER = (10.745, 106.670)
# Sample regions user called out: west An Lac, east Cat Lai, near user
REGIONS = {
    "near_user": (10.745, 106.670, 8_000),
    "west_anlac": (10.75, 106.52, 12_000),
    "east_catlai": (10.78, 106.82, 12_000),
    "center_q1": (10.78, 106.70, 8_000),
}


def bucket(dbz: float) -> str:
    if dbz < 20:
        return "<20"
    if dbz < 25:
        return "20-24"
    if dbz < 30:
        return "25-29"
    if dbz < 35:
        return "30-34"
    if dbz < 40:
        return "35-39"
    if dbz < 45:
        return "40-44"
    return "45+"


async def main() -> None:
    radar = RadarService()
    frames = await radar.get_radar_frames()
    frame = frames.frames[-1]
    up = await radar.upstream_for_frame(frame.unix_time)
    print(f"frame={frame.timestamp} MIN_DBZ={MIN_DBZ} upstream={up}")

    # cover tiles around HCMC
    tiles = set()
    for name, (lat, lon, _) in REGIONS.items():
        tiles.add(latlon_to_tile(lat, lon, RADAR_ZOOM))
    # also user tile neighbours
    ux, uy = latlon_to_tile(USER[0], USER[1], RADAR_ZOOM)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            tiles.add((ux + dx, uy + dy))

    async with httpx.AsyncClient(timeout=30) as client:
        images: dict[tuple[int, int], Image.Image] = {}
        for tx, ty in sorted(tiles):
            url = up.replace("{z}", str(RADAR_ZOOM)).replace("{x}", str(tx)).replace("{y}", str(ty))
            r = await client.get(url)
            if r.status_code != 200:
                print(f"tile {tx},{ty} status={r.status_code}")
                continue
            images[(tx, ty)] = Image.open(io.BytesIO(r.content)).convert("RGBA")
            print(f"tile {tx},{ty} bytes={len(r.content)}")

        for name, (lat, lon, radius_m) in REGIONS.items():
            counts: Counter[str] = Counter()
            n = 0
            max_dbz = 0.0
            nearest_ge25 = None
            nearest_ge35 = None
            for (tx, ty), img in images.items():
                for py in range(0, 256, 2):
                    for px in range(0, 256, 2):
                        d = pixel_dbz(*img.getpixel((px, py)))
                        if d <= 0:
                            continue
                        la, lo = tile_pixel_to_latlon(tx, ty, RADAR_ZOOM, px + 0.5, py + 0.5, 256)
                        dist = haversine_m(lat, lon, la, lo)
                        if dist > radius_m:
                            continue
                        n += 1
                        counts[bucket(d)] += 1
                        max_dbz = max(max_dbz, d)
                        if d >= 25 and (nearest_ge25 is None or dist < nearest_ge25[0]):
                            nearest_ge25 = (dist, d)
                        if d >= 35 and (nearest_ge35 is None or dist < nearest_ge35[0]):
                            nearest_ge35 = (dist, d)
            print(f"\n=== {name} r={radius_m/1000:.0f}km pixels>0={n} max={max_dbz:.1f} ===")
            for k in ("<20", "20-24", "25-29", "30-34", "35-39", "40-44", "45+"):
                print(f"  {k}: {counts[k]}")
            print(f"  nearest>=25: {nearest_ge25}")
            print(f"  nearest>=35: {nearest_ge35}")
            shown = sum(counts[k] for k in ("25-29", "30-34", "35-39", "40-44", "45+"))
            weak = sum(counts[k] for k in ("25-29", "30-34"))
            strong = sum(counts[k] for k in ("35-39", "40-44", "45+"))
            if shown:
                print(f"  map@25: weak(25-34)={weak} ({100*weak/shown:.0f}%) strong(>=35)={strong} ({100*strong/shown:.0f}%)")


if __name__ == "__main__":
    asyncio.run(main())
