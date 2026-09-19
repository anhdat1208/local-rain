from __future__ import annotations

import io

from PIL import Image

from app.services.clutter_mask import (
    CLUTTER_FRAMES,
    CLUTTER_MIN_DBZ,
    TILE_SIZE,
    hot_bitset,
    intersect_bitsets,
    is_clutter,
    pick_clutter_frames,
)
from app.services.radar_dbz import filter_tile_below_dbz, pixel_dbz

# RainViewer Universal Blue swatches
DBZ_50 = (193, 0, 0, 255)
DBZ_45 = (255, 68, 0, 255)
DBZ_40 = (255, 170, 0, 255)
DBZ_30 = (0, 85, 136, 255)
TRANSPARENT = (0, 0, 0, 0)


def tile(pixels: dict[tuple[int, int], tuple[int, int, int, int]]) -> bytes:
    image = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), TRANSPARENT)
    for (px, py), rgba in pixels.items():
        image.putpixel((px, py), rgba)
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_swatches_decode_to_expected_dbz() -> None:
    """Guards the test fixtures themselves against palette drift."""
    assert pixel_dbz(*DBZ_50) == 50
    assert pixel_dbz(*DBZ_45) == 45
    assert pixel_dbz(*DBZ_40) == 40
    assert pixel_dbz(*DBZ_30) == 30


def test_hot_bitset_only_flags_strong_echo() -> None:
    png = tile({(10, 10): DBZ_50, (11, 10): DBZ_45, (12, 10): DBZ_40, (13, 10): DBZ_30})
    bits = hot_bitset(png)

    assert is_clutter(bits, 10, 10)
    assert is_clutter(bits, 11, 10)
    # 40 and 30 dBZ sit below the clutter floor, so they can never be suppressed
    assert not is_clutter(bits, 12, 10)
    assert not is_clutter(bits, 13, 10)
    assert not is_clutter(bits, 0, 0)


def test_hot_bitset_threshold_matches_constant() -> None:
    assert CLUTTER_MIN_DBZ == 45.0
    assert pixel_dbz(*DBZ_45) >= CLUTTER_MIN_DBZ
    assert pixel_dbz(*DBZ_40) < CLUTTER_MIN_DBZ


def test_intersection_keeps_only_always_hot_pixels() -> None:
    """A moving core drops out of the intersection; a parked one survives."""
    parked = (5, 5)
    drifting = [(20, 20), (21, 20), (22, 20)]
    frames = [
        hot_bitset(tile({parked: DBZ_50, drifting[i]: DBZ_50}))
        for i in range(len(drifting))
    ]

    mask = intersect_bitsets(frames)

    assert is_clutter(mask, *parked)
    for cell in drifting:
        assert not is_clutter(mask, *cell)


def test_intersection_of_single_frame_is_that_frame() -> None:
    bits = hot_bitset(tile({(7, 9): DBZ_50}))
    assert intersect_bitsets([bits]) == bits


def test_is_clutter_is_false_for_missing_mask() -> None:
    assert not is_clutter(None, 0, 0)
    assert not is_clutter(b"", 0, 0)


def test_is_clutter_ignores_out_of_range_pixels() -> None:
    bits = hot_bitset(tile({(1, 1): DBZ_50}))
    assert not is_clutter(bits, TILE_SIZE * 4, TILE_SIZE * 4)


def test_pick_clutter_frames_needs_full_window() -> None:
    """Fail open: without enough history we must not guess at clutter."""
    times = list(range(100, 100 + CLUTTER_FRAMES - 1))
    assert pick_clutter_frames(times, newest=times[-1]) is None


def test_pick_clutter_frames_takes_the_window_ending_at_newest() -> None:
    times = list(range(0, 40))
    picked = pick_clutter_frames(times, newest=30)

    assert picked is not None
    assert len(picked) == CLUTTER_FRAMES
    assert picked[-1] == 30
    assert picked == list(range(30 - CLUTTER_FRAMES + 1, 31))


def test_pick_clutter_frames_ignores_future_nowcast_frames() -> None:
    """Nowcast frames sit after `newest`; extrapolated rain is not evidence of clutter."""
    times = list(range(0, 40))
    picked = pick_clutter_frames(times, newest=20)

    assert picked is not None
    assert max(picked) == 20


def test_filter_drops_clutter_pixels_but_keeps_real_rain() -> None:
    real = (40, 40)
    clutter = (41, 41)
    png = tile({real: DBZ_50, clutter: DBZ_50})
    mask = hot_bitset(tile({clutter: DBZ_50}))

    plain = Image.open(io.BytesIO(filter_tile_below_dbz(png))).convert("RGBA")
    masked = Image.open(io.BytesIO(filter_tile_below_dbz(png, clutter=mask))).convert("RGBA")

    assert plain.getpixel(real)[3] > 0
    assert plain.getpixel(clutter)[3] > 0

    assert masked.getpixel(real) == plain.getpixel(real)
    assert masked.getpixel(clutter)[3] == 0


def test_filter_without_mask_is_unchanged() -> None:
    png = tile({(3, 3): DBZ_50, (60, 60): DBZ_40})
    assert filter_tile_below_dbz(png, clutter=None) == filter_tile_below_dbz(png)


def test_filter_never_hides_echo_below_the_clutter_floor() -> None:
    """A mask bit on a weak pixel is harmless, but prove the floor holds either way."""
    spot = (70, 70)
    png = tile({spot: DBZ_40})
    # Hand-build a mask bit for a pixel that hot_bitset would never flag
    bits = bytearray(TILE_SIZE * TILE_SIZE // 8)
    index = spot[1] * TILE_SIZE + spot[0]
    bits[index >> 3] |= 1 << (index & 7)

    assert not is_clutter(hot_bitset(png), *spot)
    masked = Image.open(
        io.BytesIO(filter_tile_below_dbz(png, clutter=bytes(bits)))
    ).convert("RGBA")
    assert masked.getpixel(spot)[3] == 0
