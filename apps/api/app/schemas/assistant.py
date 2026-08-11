from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)


class SelectedCellContext(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class ViewportContext(BaseModel):
    north: float
    south: float
    east: float
    west: float
    zoom: float = Field(..., ge=0, le=22)


class SessionContext(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    lang: str = Field(default="vi", pattern="^(vi|en)$")
    selected_cell: SelectedCellContext | None = Field(default=None, alias="selectedCell")
    radar_timestamp: str | None = Field(default=None, alias="radarTimestamp")
    viewport: ViewportContext | None = None

    model_config = ConfigDict(populate_by_name=True)


class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    context: SessionContext


class WeatherFactsPayload(BaseModel):
    distance_m: float | None = Field(default=None, alias="distanceM")
    direction: str | None = None
    motion_direction: str | None = Field(default=None, alias="motionDirection")
    speed_kmh: float | None = Field(default=None, alias="speedKmh")
    eta_minutes: int | None = Field(default=None, alias="etaMinutes")
    trend: str | None = None
    approaching: bool | None = None
    confidence: int | None = None

    model_config = ConfigDict(populate_by_name=True)


class AssistantAction(BaseModel):
    type: Literal["highlight_rain_cell"] = "highlight_rain_cell"
    latitude: float
    longitude: float


class AssistantSSEEvent(BaseModel):
    type: Literal[
        "status",
        "text_delta",
        "weather_facts",
        "action",
        "done",
        "error",
    ]
    message: str | None = None
    content: str | None = None
    facts: WeatherFactsPayload | None = None
    action: AssistantAction | None = None
    code: str | None = None


def sse_payload(event: AssistantSSEEvent | dict[str, Any]) -> str:
    if isinstance(event, AssistantSSEEvent):
        data = event.model_dump(by_alias=True, exclude_none=True)
    else:
        data = {k: v for k, v in event.items() if v is not None}
    import json

    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
