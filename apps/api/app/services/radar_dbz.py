from __future__ import annotations

import io
import math
from functools import lru_cache

from PIL import Image

# Map only paints cells likely to wet the ground. Soft drizzle (25–34) is used
# for nearest-rain advice, not for the overlay — RainViewer paints a lot of
# non-raining fringe in that band over Vietnam.
MAP_MIN_DBZ = 35
MIN_DBZ = MAP_MIN_DBZ
MAX_DBZ = 60
COLOR_MATCH_MAX_DIST = 48.0

# RainViewer Universal Blue (rain) — first series in official color table
UNIVERSAL_BLUE_RAIN: tuple[tuple[int, int, int, int], ...] = (
    (136, 221, 238, 15),
    (108, 209, 235, 16),
    (81, 197, 232, 17),
    (54, 186, 229, 18),
    (27, 174, 226, 19),
    (0, 163, 224, 20),
    (0, 154, 213, 21),
    (0, 145, 202, 22),
    (0, 136, 191, 23),
    (0, 127, 180, 24),
    (0, 119, 170, 25),
    (0, 112, 163, 26),
    (0, 105, 156, 27),
    (0, 98, 149, 28),
    (0, 91, 142, 29),
    (0, 85, 136, 30),
    (0, 81, 128, 31),
    (0, 78, 120, 32),
    (0, 74, 112, 33),
    (0, 71, 104, 34),
    (255, 238, 0, 35),
    (255, 224, 0, 36),
    (255, 210, 0, 37),
    (255, 197, 0, 38),
    (255, 183, 0, 39),
    (255, 170, 0, 40),
    (255, 159, 0, 41),
    (255, 149, 0, 42),
    (255, 139, 0, 43),
    (255, 129, 0, 44),
    (255, 68, 0, 45),
    (242, 54, 0, 46),
    (230, 40, 0, 47),
    (217, 27, 0, 48),
    (205, 13, 0, 49),
    (193, 0, 0, 50),
    (168, 0, 0, 51),
    (143, 0, 0, 52),
    (118, 0, 0, 53),
    (93, 0, 0, 54),
    (255, 170, 255, 55),
    (255, 159, 255, 56),
    (255, 149, 255, 57),
    (255, 139, 255, 58),
    (255, 129, 255, 59),
    (255, 119, 255, 60),
)

# Quantized RGB → precomputed map pixel. Avoids 46-color distance scan per pixel.
_FILTER_SHIFT = 3  # 8-level bins → 32³ = 32768 entries
_FILTER_BINS = 256 >> _FILTER_SHIFT
_FILTER_RGBA_LUT: list[tuple[int, int, int, int]] | None = None


@lru_cache(maxsize=65_536)
def _rgb_dbz(r: int, g: int, b: int) -> float:
    brightness = (r + g + b) / 3.0
    chroma = max(r, g, b) - min(r, g, b)
    if chroma < 10 and brightness > 220:
        return 0.0
    if chroma < 8 and brightness < 20:
        return 0.0

    best_dbz = 0.0
    best_dist = COLOR_MATCH_MAX_DIST
    for pr, pg, pb, dbz in UNIVERSAL_BLUE_RAIN:
        dist = math.sqrt((r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2)
        if dist < best_dist:
            best_dist = dist
            best_dbz = float(dbz)
    return best_dbz if best_dist < COLOR_MATCH_MAX_DIST else 0.0


def pixel_dbz(r: int, g: int, b: int, a: int) -> float:
    if a < 80:
        return 0.0
    # Radar tiles reuse a tiny palette, so caching by colour keeps full-tile scans cheap
    return _rgb_dbz(r, g, b)


def intensity_from_dbz(dbz: float) -> float:
    return max(0.0, min(1.0, (dbz - MIN_DBZ) / (MAX_DBZ - MIN_DBZ)))


def dbz_to_cool_color(dbz: float) -> tuple[int, int, int]:
    """Use cooler rain palette to avoid 'heatmap' impression."""
    if dbz < 35:
        return (78, 195, 247)  # light cyan
    if dbz < 40:
        return (56, 151, 240)  # sky blue
    if dbz < 45:
        return (43, 102, 230)  # blue
    if dbz < 50:
        return (97, 77, 214)  # violet
    if dbz < 55:
        return (128, 92, 224)  # vivid violet
    return (173, 109, 232)  # magenta-purple for strongest cores


def _filter_lut() -> list[tuple[int, int, int, int]]:
    global _FILTER_RGBA_LUT
    if _FILTER_RGBA_LUT is not None:
        return _FILTER_RGBA_LUT

    transparent = (0, 0, 0, 0)
    lut: list[tuple[int, int, int, int]] = [transparent] * (
        _FILTER_BINS * _FILTER_BINS * _FILTER_BINS
    )
    half = 1 << (_FILTER_SHIFT - 1)
    for rq in range(_FILTER_BINS):
        for gq in range(_FILTER_BINS):
            for bq in range(_FILTER_BINS):
                r = (rq << _FILTER_SHIFT) + half
                g = (gq << _FILTER_SHIFT) + half
                b = (bq << _FILTER_SHIFT) + half
                dbz = _rgb_dbz(r, g, b)
                idx = (rq * _FILTER_BINS + gq) * _FILTER_BINS + bq
                if dbz < MAP_MIN_DBZ:
                    lut[idx] = transparent
                    continue
                nr, ng, nb = dbz_to_cool_color(dbz)
                boost = intensity_from_dbz(dbz)
                alpha = min(255, max(135, int(150 + boost * 105)))
                lut[idx] = (nr, ng, nb, alpha)
    _FILTER_RGBA_LUT = lut
    return lut


def filter_tile_below_dbz(png_bytes: bytes, min_dbz: float = MAP_MIN_DBZ) -> bytes:
    """Hide weak fringe; map shows ≥35 dBZ cores that usually mean real rain."""
    image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    src = memoryview(image.tobytes())
    out = bytearray(len(src))
    # Fast path uses the quantized LUT (same threshold as MAP_MIN_DBZ).
    if min_dbz == MAP_MIN_DBZ:
        lut = _filter_lut()
        bins = _FILTER_BINS
        shift = _FILTER_SHIFT
        for i in range(0, len(src), 4):
            a = src[i + 3]
            if a < 80:
                continue
            idx = (
                ((src[i] >> shift) * bins + (src[i + 1] >> shift)) * bins
                + (src[i + 2] >> shift)
            )
            nr, ng, nb, na = lut[idx]
            if na == 0:
                continue
            out[i] = nr
            out[i + 1] = ng
            out[i + 2] = nb
            out[i + 3] = na
    else:
        pixels = image.load()
        width, height = image.size
        for y in range(height):
            for x in range(width):
                r, g, b, a = pixels[x, y]
                dbz = pixel_dbz(r, g, b, a)
                if a < 80 or dbz < min_dbz:
                    continue
                nr, ng, nb = dbz_to_cool_color(dbz)
                boost = intensity_from_dbz(dbz)
                alpha = min(255, max(135, int(150 + boost * 105)))
                oi = (y * width + x) * 4
                out[oi] = nr
                out[oi + 1] = ng
                out[oi + 2] = nb
                out[oi + 3] = alpha

    filtered = Image.frombytes("RGBA", image.size, bytes(out))
    buf = io.BytesIO()
    filtered.save(buf, format="PNG", compress_level=3)
    return buf.getvalue()
