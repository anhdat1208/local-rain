from __future__ import annotations

import io

from PIL import Image

from app.services.clutter_track import cell_index
from app.services.radar_dbz import filter_tile_below_dbz, mask_clutter_in_tile
from app.utils.geo import tile_pixel_to_latlon


def test_mask_clutter_zeros_matching_pixels() -> None:
    # Build a tile with one opaque magenta-ish pixel after cool remap path
    # Use Universal Blue ~55 dBZ colour so filter keeps it
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    # RainViewer Universal Blue ~55 dBZ
    img.putpixel((10, 20), (255, 170, 255, 200))
    raw = io.BytesIO()
    img.save(raw, format="PNG")
    filtered = filter_tile_below_dbz(raw.getvalue())

    lat, lon = tile_pixel_to_latlon(101, 60, 7, 10.5, 20.5, 256)
    clutter = {cell_index(lat, lon)}
    masked = mask_clutter_in_tile(filtered, z=7, x=101, y=60, clutter_cells=clutter)
    out = Image.open(io.BytesIO(masked)).convert("RGBA")
    assert out.getpixel((10, 20))[3] == 0


def test_mask_clutter_keeps_other_pixels() -> None:
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    img.putpixel((10, 20), (255, 170, 255, 200))
    raw = io.BytesIO()
    img.save(raw, format="PNG")
    filtered = filter_tile_below_dbz(raw.getvalue())
    masked = mask_clutter_in_tile(
        filtered, z=7, x=101, y=60, clutter_cells={(0, 0)}
    )
    out = Image.open(io.BytesIO(masked)).convert("RGBA")
    assert out.getpixel((10, 20))[3] > 0
