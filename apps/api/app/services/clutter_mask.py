"""Stateless detection of parked radar echoes (ground clutter / anomalous propagation).

RainViewer mosaics over Vietnam can hold 45–55 dBZ on a fixed footprint for hours.
Remapped to violet and overzoomed to street level, one such 1.2 km pixel washes a whole
viewport and makes a dry evening look like a downpour.

Real convection never stands still: measured against live RainViewer history, requiring
a pixel to stay hot across 9 consecutive frames (~90 min) flagged 0% of the echoes in
two moving-rain control regions, while the sticky HCMC echo stayed flagged in 13/13.

Unlike a tracker that accumulates state over time, the evidence here comes from the
frame list RainViewer already publishes, so a cold cache is never a blind spot. Every
failure path returns "no clutter" — showing rain that is not there beats hiding rain
that is.
"""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import Iterable, Mapping, Sequence

import httpx
from PIL import Image

from app.core.redis import get_redis
from app.services.radar_dbz import pixel_dbz

# Only strong echo can be clutter; drizzle is never worth suppressing.
CLUTTER_MIN_DBZ = 45.0
# Consecutive frames a pixel must stay hot. Frames are 10 min apart, so ~90 min.
CLUTTER_FRAMES = 9
# Below this zoom a radar pixel is coarser than a district and the wash is not the
# problem we are solving, so skip the extra upstream fetches entirely.
CLUTTER_MIN_ZOOM = 6

TILE_SIZE = 256
_BITSET_BYTES = TILE_SIZE * TILE_SIZE // 8
# Hot bitsets must outlive the whole lookback window; masks rotate with each frame.
_HOT_TTL_SECONDS = 3 * 60 * 60
_MASK_TTL_SECONDS = 30 * 60
_EMPTY_MASK = bytes(_BITSET_BYTES)


def hot_bitset(png_bytes: bytes) -> bytes:
    """One bit per pixel, set when that pixel carries a strong echo."""
    image = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    if image.size != (TILE_SIZE, TILE_SIZE):
        image = image.resize((TILE_SIZE, TILE_SIZE), Image.NEAREST)

    src = memoryview(image.tobytes())
    bits = bytearray(_BITSET_BYTES)
    for i in range(0, len(src), 4):
        if src[i + 3] < 80:
            continue
        if pixel_dbz(src[i], src[i + 1], src[i + 2], src[i + 3]) < CLUTTER_MIN_DBZ:
            continue
        index = i >> 2
        bits[index >> 3] |= 1 << (index & 7)
    return bytes(bits)


def intersect_bitsets(masks: Sequence[bytes]) -> bytes:
    """Pixels hot in every frame — the parked footprint."""
    if not masks:
        return _EMPTY_MASK
    acc = int.from_bytes(masks[0], "big")
    for mask in masks[1:]:
        acc &= int.from_bytes(mask, "big")
    return acc.to_bytes(_BITSET_BYTES, "big")


def is_clutter(mask: bytes | None, px: int, py: int) -> bool:
    if not mask:
        return False
    if not (0 <= px < TILE_SIZE and 0 <= py < TILE_SIZE):
        return False
    index = py * TILE_SIZE + px
    byte = index >> 3
    if byte >= len(mask):
        return False
    return bool(mask[byte] & (1 << (index & 7)))


def pick_clutter_frames(times: Iterable[int], newest: int) -> list[int] | None:
    """The lookback window ending at `newest`, or None when history is too short.

    Frames after `newest` are nowcast extrapolations, so they are not evidence.
    """
    past = sorted(t for t in times if t <= newest)
    if len(past) < CLUTTER_FRAMES:
        return None
    return past[-CLUTTER_FRAMES:]


def _mask_key(newest: int, z: int, x: int, y: int) -> str:
    return f"radar:clutter:v1:{newest}:{z}:{x}:{y}"


def _hot_key(unix_time: int, z: int, x: int, y: int) -> str:
    return f"radar:hot:v1:{unix_time}:{z}:{x}:{y}"


def _read_b64(key: str) -> bytes | None:
    try:
        raw = get_redis().get(key)
    except Exception:
        return None
    if not raw:
        return None
    try:
        return base64.b64decode(raw)
    except Exception:
        return None


def _write_b64(key: str, value: bytes, ttl: int) -> None:
    try:
        get_redis().setex(key, ttl, base64.b64encode(value).decode("ascii"))
    except Exception:
        return


def peek_clutter_mask(newest: int, z: int, x: int, y: int) -> bytes | None:
    """Cached mask only. Used where paying for upstream fetches is not worth it."""
    return _read_b64(_mask_key(newest, z, x, y))


async def _hot_for_frame(
    client: httpx.AsyncClient,
    upstream: str,
    unix_time: int,
    z: int,
    x: int,
    y: int,
) -> bytes | None:
    key = _hot_key(unix_time, z, x, y)
    cached = _read_b64(key)
    if cached is not None:
        return cached

    url = upstream.replace("{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
    try:
        response = await client.get(url, timeout=12.0)
        if response.status_code != 200 or not response.content:
            return None
        bits = hot_bitset(response.content)
    except Exception:
        return None

    _write_b64(key, bits, _HOT_TTL_SECONDS)
    return bits


async def clutter_mask(
    *,
    client: httpx.AsyncClient,
    upstreams: Mapping[int, str],
    newest: int,
    z: int,
    x: int,
    y: int,
) -> bytes | None:
    """Parked-echo mask for one tile, or None when we cannot tell.

    Consecutive frames mean a new frame only costs one fresh decode: the other eight
    bitsets are still cached from the previous cycle.
    """
    if z < CLUTTER_MIN_ZOOM:
        return None

    window = pick_clutter_frames(upstreams.keys(), newest)
    if window is None:
        return None

    cached = _read_b64(_mask_key(newest, z, x, y))
    if cached is not None:
        return cached

    bitsets = await asyncio.gather(
        *(
            _hot_for_frame(client, upstreams[unix_time], unix_time, z, x, y)
            for unix_time in window
        )
    )
    # A missing frame means incomplete evidence, so decline rather than over-suppress
    if any(bits is None for bits in bitsets):
        return None

    mask = intersect_bitsets([bits for bits in bitsets if bits is not None])
    _write_b64(_mask_key(newest, z, x, y), mask, _MASK_TTL_SECONDS)
    return mask
