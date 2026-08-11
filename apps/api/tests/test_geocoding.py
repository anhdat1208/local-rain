from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.geocoding import GeocodingService


def test_cache_key_rounds_to_neighborhood_grid() -> None:
    key = GeocodingService._cache_key(10.7729, 106.6927, "vi")
    assert key == "geocode:v2:vi:10.773:106.693"


def test_is_coordinate_fallback() -> None:
    assert GeocodingService._is_coordinate_fallback("10.7729, 106.6927")
    assert not GeocodingService._is_coordinate_fallback("Phường Bến Thành")


def test_format_label_prefers_suburb() -> None:
    service = GeocodingService()
    label = service._format_label(
        {
            "address": {
                "suburb": "Phường Bến Thành",
                "city": "Thành phố Hồ Chí Minh",
                "country": "Việt Nam",
            },
            "display_name": "Khu phố 2, Phường Bến Thành, ...",
        }
    )
    assert label == "Phường Bến Thành"


@pytest.mark.asyncio
async def test_reverse_geocode_uses_redis_cache() -> None:
    service = GeocodingService()
    mock_redis = MagicMock()
    mock_redis.get.return_value = "Phường Bến Thành"

    with patch("app.services.geocoding.get_redis", return_value=mock_redis):
        label = await service.reverse_geocode(10.7729, 106.6927, lang="vi")

    assert label == "Phường Bến Thành"
    mock_redis.get.assert_called_once()


@pytest.mark.asyncio
async def test_reverse_geocode_caches_nominatim_result() -> None:
    service = GeocodingService()
    mock_redis = MagicMock()
    mock_redis.get.return_value = None

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "address": {"suburb": "Phường Bến Thành", "city": "HCMC"},
    }

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.geocoding.get_redis", return_value=mock_redis),
        patch("app.services.geocoding.get_http_client", return_value=mock_client),
    ):
        label = await service.reverse_geocode(10.7729, 106.6927, lang="vi")

    assert label == "Phường Bến Thành"
    mock_redis.setex.assert_called_once()
    args = mock_redis.setex.call_args.args
    assert args[0].startswith("geocode:v2:vi:")
    assert args[2] == "Phường Bến Thành"
