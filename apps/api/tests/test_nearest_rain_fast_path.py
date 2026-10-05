from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.radar import RadarFrameSchema, RadarResponse
from app.services.clouds import CloudCoverSample
from app.services.nearest_rain import MotionContext, NearestRainService


def _frames() -> RadarResponse:
    return RadarResponse(
        frames=[
            RadarFrameSchema(
                timestamp="2026-10-05T00:00:00+00:00",
                unix_time=1_700_000_000,
                tile_url_template=(
                    "https://api.example/api/radar/tiles/"
                    "1700000000/{z}/{x}/{y}.png"
                ),
            )
        ],
        generated_at="2026-10-05T00:00:00+00:00",
        host="https://example",
    )


def _service() -> NearestRainService:
    radar = MagicMock()
    radar.get_radar_frames = AsyncMock(return_value=_frames())
    radar.upstream_for_frame = AsyncMock(return_value="https://rv/{z}/{x}/{y}")
    radar.upstream_map = MagicMock(
        return_value={1_700_000_000: "https://rv/{z}/{x}/{y}"}
    )
    clouds = MagicMock()
    clouds.sample_cover = AsyncMock(
        return_value=CloudCoverSample(cover=0.1, mode="day", ok=True)
    )
    return NearestRainService(radar, clouds)


@pytest.mark.asyncio
async def test_first_cold_skips_shared_motion_context() -> None:
    service = _service()

    with (
        patch.object(service, "_read_cache", return_value=None),
        patch.object(service, "_read_velocity_cache", return_value=None),
        patch.object(service, "_velocity_warm_requested", return_value=False),
        patch.object(service, "_mark_velocity_warm") as mark,
        patch.object(service, "_find_nearest_hit", AsyncMock(return_value=None)) as hit,
        patch.object(service, "_shared_motion_context", AsyncMock()) as motion,
        patch.object(service, "_write_cache") as write,
        patch("app.services.nearest_rain.get_http_client", return_value=MagicMock()),
    ):
        result = await service.find_nearest(10.77, 106.70, lang="vi")

    assert result.motion_pending is True
    motion.assert_not_called()
    hit.assert_awaited()
    mark.assert_called_once()
    assert write.call_args.args[0].startswith("nearest-rain:v23:")


@pytest.mark.asyncio
async def test_second_request_builds_motion_when_warm_marked() -> None:
    service = _service()
    motion_ctx = MotionContext(
        current_field={},
        baselines=[],
        velocity=(0.01, -0.02),
    )

    with (
        patch.object(
            service,
            "_read_cache",
            return_value=MagicMock(motion_pending=True),
        ),
        patch.object(service, "_read_velocity_cache", return_value=None),
        patch.object(service, "_velocity_warm_requested", return_value=True),
        patch.object(service, "_clear_velocity_warm") as clear,
        patch.object(service, "_find_nearest_hit", AsyncMock(return_value=None)),
        patch.object(
            service,
            "_shared_motion_context",
            AsyncMock(return_value=motion_ctx),
        ) as motion,
        patch.object(service, "_write_cache"),
        patch("app.services.nearest_rain.get_http_client", return_value=MagicMock()),
    ):
        result = await service.find_nearest(10.77, 106.70, lang="vi")

    assert result.motion_pending is False
    motion.assert_awaited()
    clear.assert_called_once()


@pytest.mark.asyncio
async def test_motion_warm_failure_still_returns_valid_response() -> None:
    service = _service()

    with (
        patch.object(
            service,
            "_read_cache",
            return_value=MagicMock(motion_pending=True),
        ),
        patch.object(service, "_read_velocity_cache", return_value=None),
        patch.object(service, "_velocity_warm_requested", return_value=True),
        patch.object(service, "_clear_velocity_warm") as clear,
        patch.object(service, "_find_nearest_hit", AsyncMock(return_value=None)),
        patch.object(
            service,
            "_shared_motion_context",
            AsyncMock(side_effect=RuntimeError("motion unavailable")),
        ),
        patch.object(service, "_write_cache"),
        patch("app.services.nearest_rain.get_http_client", return_value=MagicMock()),
    ):
        result = await service.find_nearest(10.77, 106.70, lang="vi")

    assert result.motion_pending is False
    assert result.motion_direction is None
    assert result.speed_kmh == 0
    clear.assert_called_once()


def test_velocity_warm_marker_uses_expected_key_and_ttl() -> None:
    service = _service()
    current = _frames().frames[0]
    redis = MagicMock()

    with patch("app.services.nearest_rain.get_redis", return_value=redis):
        key = service._velocity_warm_key(current, 10.7704, 106.7004)
        service._mark_velocity_warm(key)
        assert service._velocity_warm_requested(key) is True
        service._clear_velocity_warm(key)

    assert key == "rain-velocity:warm:v1:1700000000:10.77:106.7"
    redis.setex.assert_called_once_with(key, 90, "1")
    redis.get.assert_called_once_with(key)
    redis.delete.assert_called_once_with(key)
