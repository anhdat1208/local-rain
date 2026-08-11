from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from google.genai import types

from app.core.config import get_settings
from app.schemas.assistant import AssistantChatRequest, AssistantSSEEvent
from app.services.assistant.gemini_client import GeminiAssistantClient, get_gemini_client
from app.services.assistant.rate_limit import RateLimitExceeded, check_rate_limit
from app.services.assistant.system_prompt import build_context_prefix, initial_status

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 10


class AssistantOrchestrator:
    def __init__(self, gemini: GeminiAssistantClient | None = None) -> None:
        self._gemini = gemini or get_gemini_client()

    async def handle(
        self,
        request: AssistantChatRequest,
        client_ip: str,
    ) -> AsyncIterator[AssistantSSEEvent]:
        request_id = uuid.uuid4().hex[:12]
        lang = request.context.lang if request.context.lang in ("vi", "en") else "vi"
        settings = get_settings()

        if not self._gemini.available:
            yield AssistantSSEEvent(
                type="error",
                code="assistant_unconfigured",
                message=(
                    "Trợ lý AI chưa được cấu hình trên server."
                    if lang == "vi"
                    else "AI assistant is not configured on this server."
                ),
            )
            return

        try:
            check_rate_limit(
                client_ip,
                limit=settings.assistant_rate_limit,
                window_seconds=settings.assistant_rate_window_seconds,
            )
        except RateLimitExceeded:
            yield AssistantSSEEvent(
                type="error",
                code="rate_limited",
                message=(
                    "Bạn hỏi hơi nhiều — thử lại sau vài phút nhé."
                    if lang == "vi"
                    else "Too many requests — please try again in a few minutes."
                ),
            )
            return

        logger.info("assistant request_id=%s lang=%s ip=%s", request_id, lang, _mask_ip(client_ip))
        yield AssistantSSEEvent(type="status", message=initial_status(lang))

        contents = _build_contents(request)
        try:
            async for event in self._gemini.chat_stream(contents, lang=lang):
                yield event
        except Exception:
            logger.exception("assistant request_id=%s failed", request_id)
            yield AssistantSSEEvent(
                type="error",
                code="assistant_failed",
                message=(
                    "Không kết nối được trợ lý AI lúc này."
                    if lang == "vi"
                    else "Could not reach the AI assistant right now."
                ),
            )


def _build_contents(request: AssistantChatRequest) -> list[types.Content]:
    contents: list[types.Content] = []
    history = request.history[-MAX_HISTORY_TURNS:]
    for msg in history:
        role = "user" if msg.role == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg.content)]))

    ctx = request.context.model_dump(by_alias=True, exclude_none=True)
    prefix = build_context_prefix(ctx)
    user_text = f"{prefix}User: {request.message.strip()}"
    contents.append(types.Content(role="user", parts=[types.Part(text=user_text)]))
    return contents


def _mask_ip(ip: str) -> str:
    if not ip or ip == "unknown":
        return "unknown"
    if ":" in ip:
        parts = ip.split(":")
        return f"{parts[0]}:…" if parts else ip
    octets = ip.split(".")
    if len(octets) == 4:
        return f"{octets[0]}.{octets[1]}.x.x"
    return ip[:8] + "…"


def get_assistant_orchestrator() -> AssistantOrchestrator:
    return AssistantOrchestrator()
