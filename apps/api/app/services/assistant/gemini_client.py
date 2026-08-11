from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from typing import Any

from google import genai
from google.genai import types

from app.core.config import get_settings
from app.schemas.assistant import AssistantSSEEvent
from app.services.assistant.system_prompt import SYSTEM_INSTRUCTION
from app.services.assistant.tool_schemas import GEMINI_TOOLS
from app.services.assistant.tools import WeatherTools

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5


class GeminiAssistantClient:
    def __init__(
        self,
        tools: WeatherTools | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.gemini_api_key
        self._model = model or settings.gemini_model
        self._tools = tools or WeatherTools()
        self._client: genai.Client | None = None

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def chat_stream(
        self,
        contents: list[types.Content],
        lang: str,
    ) -> AsyncIterator[AssistantSSEEvent]:
        if not self.available:
            yield AssistantSSEEvent(
                type="error",
                code="assistant_unconfigured",
                message="AI assistant is not configured on this server.",
            )
            return

        client = self._get_client()
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=[GEMINI_TOOLS],
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            temperature=0.4,
        )

        working = list(contents)
        tool_events: list[dict[str, Any]] = []

        for round_idx in range(MAX_TOOL_ROUNDS):
            started = time.perf_counter()
            response = await client.aio.models.generate_content(
                model=self._model,
                contents=working,
                config=config,
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.info("gemini round=%s latency_ms=%s", round_idx, latency_ms)

            function_calls = _extract_function_calls(response)
            if not function_calls:
                break

            model_content = response.candidates[0].content if response.candidates else None
            if model_content is not None:
                working.append(model_content)

            for call in function_calls:
                name = call.name or ""
                args = dict(call.args or {})
                yield AssistantSSEEvent(type="status", message=_tool_status(name, lang))

                tool_started = time.perf_counter()
                result = await self._tools.execute(name, args)
                tool_ms = int((time.perf_counter() - tool_started) * 1000)
                logger.info("assistant tool=%s duration_ms=%s", name, tool_ms)
                tool_events.append({"tool": name, "result": result})

                working.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_function_response(
                                name=name,
                                response={"result": result},
                            )
                        ],
                    )
                )
        else:
            yield AssistantSSEEvent(
                type="error",
                code="tool_limit",
                message="Too many tool calls for one question.",
            )
            return

        # Stream final natural-language answer
        stream = await client.aio.models.generate_content_stream(
            model=self._model,
            contents=working,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.4,
            ),
        )
        async for chunk in stream:
            text = chunk.text
            if text:
                yield AssistantSSEEvent(type="text_delta", content=text)

        for extra in _derive_side_events(tool_events):
            yield extra

        yield AssistantSSEEvent(type="done")


def _extract_function_calls(response: Any) -> list[types.FunctionCall]:
    calls: list[types.FunctionCall] = []
    if not response.candidates:
        return calls
    content = response.candidates[0].content
    if not content or not content.parts:
        return calls
    for part in content.parts:
        if part.function_call:
            calls.append(part.function_call)
    return calls


def _tool_status(name: str, lang: str) -> str:
    from app.services.assistant.system_prompt import tool_status

    return tool_status(name, lang)


def _derive_side_events(tool_events: list[dict[str, Any]]) -> list[AssistantSSEEvent]:
    events: list[AssistantSSEEvent] = []
    for entry in tool_events:
        result = entry.get("result") or {}
        if not isinstance(result, dict):
            continue
        data = result.get("data")
        if isinstance(data, dict) and data.get("hasRain"):
            lat = data.get("rainLatitude")
            lng = data.get("rainLongitude")
            if lat is not None and lng is not None:
                from app.schemas.assistant import AssistantAction, WeatherFactsPayload

                events.append(
                    AssistantSSEEvent(
                        type="action",
                        action=AssistantAction(type="highlight_rain_cell", latitude=lat, longitude=lng),
                    )
                )
                events.append(
                    AssistantSSEEvent(
                        type="weather_facts",
                        facts=WeatherFactsPayload(
                            distanceM=data.get("distanceM"),
                            direction=data.get("direction"),
                            motionDirection=data.get("motionDirection"),
                            speedKmh=data.get("speedKmh"),
                            etaMinutes=data.get("etaMinutes"),
                            trend=data.get("trend"),
                            approaching=data.get("approaching"),
                            confidence=data.get("confidence"),
                        ),
                    )
                )
        cell = result.get("cell")
        if isinstance(cell, dict) and result.get("found"):
            from app.schemas.assistant import AssistantAction

            events.append(
                AssistantSSEEvent(
                    type="action",
                    action=AssistantAction(
                        type="highlight_rain_cell",
                        latitude=float(cell["latitude"]),
                        longitude=float(cell["longitude"]),
                    ),
                )
            )
    return events


def get_gemini_client() -> GeminiAssistantClient:
    return GeminiAssistantClient()
