from __future__ import annotations

import base64
import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.services.clutter_mask import TILE_SIZE
from app.services.radar import RadarService


def _png() -> bytes:
    image = Image.new("RGBA", (TILE_SIZE, TILE_SIZE), (193, 0, 0, 255))
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_z7_miss_uses_peek_not_full_clutter_mask() -> None:
    raw = _png()
    service = RadarService()
    redis = MagicMock()
    redis.get.return_value = None

    client = AsyncMock()
    response = MagicMock()
    response.content = raw
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    with (
        patch("app.services.radar.get_redis", return_value=redis),
        patch("app.services.radar.get_http_client", return_value=client),
        patch.object(service, "upstream_map", return_value={1_700_000_000: "https://example/{z}/{x}/{y}"}),
        patch.object(service, "newest_past_unix", return_value=1_700_000_000),
        patch.object(service, "upstream_for_frame", AsyncMock(return_value="https://example/{z}/{x}/{y}")),
        patch("app.services.radar.peek_clutter_mask", return_value=None) as peek,
        patch("app.services.radar.clutter_mask", AsyncMock()) as full_mask,
        patch("app.services.radar.filter_tile_below_dbz", return_value=raw) as filt,
    ):
        png, kind = await service.get_filtered_tile_with_kind(1_700_000_000, 7, 100, 60)

    assert kind == "fast"
    assert png == raw
    peek.assert_called_once()
    full_mask.assert_not_called()
    filt.assert_called_once()
    assert filt.call_args.kwargs.get("clutter") is None or filt.call_args.args[1:] == ()


@pytest.mark.asyncio
async def test_z5_miss_still_awaits_clutter_mask() -> None:
    raw = _png()
    service = RadarService()
    redis = MagicMock()
    redis.get.return_value = None
    mask = b"\x00" * (TILE_SIZE * TILE_SIZE // 8)

    client = AsyncMock()
    response = MagicMock()
    response.content = raw
    response.raise_for_status = MagicMock()
    client.get.return_value = response

    with (
        patch("app.services.radar.get_redis", return_value=redis),
        patch("app.services.radar.get_http_client", return_value=client),
        patch.object(service, "upstream_map", return_value={1_700_000_000: "https://example/{z}/{x}/{y}"}),
        patch.object(service, "newest_past_unix", return_value=1_700_000_000),
        patch.object(service, "upstream_for_frame", AsyncMock(return_value="https://example/{z}/{x}/{y}")),
        patch("app.services.radar.clutter_mask", AsyncMock(return_value=mask)) as full_mask,
        patch("app.services.radar.filter_tile_below_dbz", return_value=raw),
    ):
        png, kind = await service.get_filtered_tile_with_kind(1_700_000_000, 5, 10, 20)

    assert kind == "full"
    full_mask.assert_awaited()


@pytest.mark.asyncio
async def test_full_cache_hit_skips_upstream() -> None:
    raw = _png()
    service = RadarService()
    redis = MagicMock()
    # First redis.get is full cache key
    redis.get.side_effect = [base64.b64encode(raw).decode("ascii")]

    with (
        patch("app.services.radar.get_redis", return_value=redis),
        patch("app.services.radar.get_http_client") as http,
        patch.object(service, "upstream_map", return_value={1_700_000_000: "https://example/{z}/{x}/{y}"}),
        patch.object(service, "newest_past_unix", return_value=1_700_000_000),
    ):
        png, kind = await service.get_filtered_tile_with_kind(1_700_000_000, 7, 100, 60)

    assert kind == "full"
    assert png == raw
    http.assert_not_called()
