from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.assistant import AssistantSSEEvent
from app.services.assistant.rate_limit import RateLimitExceeded, check_rate_limit
from app.services.assistant.tools import WeatherTools
from app.schemas.nearest_rain import NearestRainResponse


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_assistant_chat_requires_gemini_key(client: TestClient) -> None:
    response = client.post(
        "/api/assistant/chat",
        json={
            "message": "Có mưa không?",
            "history": [],
            "context": {"latitude": 10.74, "longitude": 106.66, "lang": "vi"},
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "assistant_unconfigured" in body or "data:" in body


@pytest.mark.asyncio
async def test_get_nearest_rain_tool_compact() -> None:
    mock_service = MagicMock()
    mock_service.find_nearest = AsyncMock(
        return_value=NearestRainResponse(
            distance=8400,
            eta=25,
            direction="NE",
            confidence=72,
            explanation="Rain NE",
            advice="Bring umbrella",
            has_rain=True,
            rain_latitude=10.75,
            rain_longitude=106.70,
            motion_direction="SW",
            speed_kmh=24,
            approaching=True,
            previous_distance=9200,
            rain_chance="medium",
            rain_chance_pct=55,
            rain_in_1h=True,
            rain_in_2h=True,
            raining_here=False,
            radar_timestamp="2026-08-11T12:00:00Z",
            radar_age_minutes=3,
            sky_state="partly",
            cloud_cover_pct=40,
        )
    )
    tools = WeatherTools(nearest_rain=mock_service)
    result = await tools.execute(
        "get_nearest_rain",
        {"latitude": 10.74, "longitude": 106.66, "lang": "vi"},
    )
    assert result["ok"] is True
    assert result["data"]["hasRain"] is True
    assert result["data"]["distanceM"] == 8400
    assert result["data"]["trend"] == "approaching"


@pytest.mark.asyncio
async def test_unknown_tool() -> None:
    tools = WeatherTools(
        nearest_rain=MagicMock(),
        radar=MagicMock(),
        geocoding=MagicMock(),
    )
    result = await tools.execute("fake_tool", {})
    assert result["error"] == "unknown_tool"


def test_rate_limit_exceeded() -> None:
    mock_redis = MagicMock()
    mock_redis.incr.return_value = 21
    with patch("app.services.assistant.rate_limit.get_redis", return_value=mock_redis):
        with pytest.raises(RateLimitExceeded):
            check_rate_limit("127.0.0.1", limit=20, window_seconds=300)


def test_sse_payload_shape() -> None:
    payload = AssistantSSEEvent(type="status", message="Checking…")
    from app.schemas.assistant import sse_payload

    text = sse_payload(payload)
    assert text.startswith("data: ")
    assert "Checking" in text
