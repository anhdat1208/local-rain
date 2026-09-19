"""End-to-end check of the clutter filter against live RainViewer data.

Uses the real production functions, so whatever this prints is what the API will do.
"""

from __future__ import annotations

import io
import math
import sys
from pathlib import Path

import httpx
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.services.clutter_mask import (  # noqa: E402
    CLUTTER_FRAMES,
    hot_bitset,
    intersect_bitsets,
    is_clutter,
    pick_clutter_frames,
)
from app.services.radar_dbz import filter_tile_below_dbz  # noqa: E402

MAPS_URL = "https://api.rainviewer.com/public/weather-maps.json"
UPSTREAM_OPTIONS = "2/0_1.png"
ZOOM = 7
RADAR_MAXZOOM = 7
RADAR_OPACITY = 0.72
BASEMAP = (242, 240, 245, 255)

SITES = {
    "HCMC (user)": (10.735, 106.665),
    "Central highlands": (12.68, 108.05),
    "Hanoi": (21.02, 105.84),
}


def deg2tile(lat: float, lng: float, z: int) -> tuple[int, int, float, float]:
    n = 2**z
    xf = (lng + 180.0) / 360.0 * n
    yf = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n
    return int(xf), int(yf), xf, yf


def painted(png: bytes) -> int:
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    return sum(1 for a in img.getchannel("A").getdata() if a > 0)


def viewport(png: bytes, px: int, py: int, out: str) -> None:
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    half = max(1, int(round(1024 / (2 ** (14 - RADAR_MAXZOOM)) / 2)))
    crop = img.crop((px - half, py - half, px + half + 1, py + half + 1))
    crop = crop.resize((900, 900), Image.NEAREST)
    canvas = Image.new("RGBA", crop.size, BASEMAP)
    alpha = crop.getchannel("A").point(lambda v: int(v * RADAR_OPACITY))
    crop.putalpha(alpha)
    canvas.alpha_composite(crop)
    canvas.convert("RGB").save(out)


def main() -> None:
    with httpx.Client(timeout=40.0) as client:
        maps = client.get(MAPS_URL).json()
        host = maps.get("host") or "https://tilecache.rainviewer.com"
        past = maps["radar"]["past"]
        times = [fr["time"] for fr in past]
        by_time = {fr["time"]: fr["path"] for fr in past}
        newest = times[-1]

        window = pick_clutter_frames(times, newest=newest)
        if window is None:
            print(f"only {len(times)} past frames, need {CLUTTER_FRAMES} — filter fails open")
            return
        print(f"lookback window: {len(window)} frames, "
              f"{(window[-1] - window[0]) / 60:.0f} min span\n")

        for name, (lat, lng) in SITES.items():
            x, y, xf, yf = deg2tile(lat, lng, ZOOM)
            upx, upy = int((xf - x) * 256), int((yf - y) * 256)

            def tile_png(unix_time: int) -> bytes:
                return client.get(
                    f"{host}{by_time[unix_time]}/256/{ZOOM}/{x}/{y}/{UPSTREAM_OPTIONS}"
                ).content

            mask = intersect_bitsets([hot_bitset(tile_png(t)) for t in window])
            raw = tile_png(newest)

            before = filter_tile_below_dbz(raw)
            after = filter_tile_below_dbz(raw, clutter=mask)
            pb, pa = painted(before), painted(after)
            removed = pb - pa

            print(f"--- {name}  tile z{ZOOM}/{x}/{y} ---")
            print(f"    painted pixels: {pb} -> {pa}   removed {removed} ({removed / pb * 100 if pb else 0:.1f}%)")
            print(f"    user pixel ({upx},{upy}) flagged as clutter: "
                  f"{'YES' if is_clutter(mask, upx, upy) else 'no'}")

            if name.startswith("HCMC"):
                viewport(before, upx, upy, "scripts/_verify_before.png")
                viewport(after, upx, upy, "scripts/_verify_after.png")
                print("    saved scripts/_verify_before.png / _verify_after.png")
            print()


if __name__ == "__main__":
    main()
