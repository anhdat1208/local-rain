from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.schemas.assistant import AssistantChatRequest, AssistantSSEEvent, sse_payload
from app.services.assistant.orchestrator import AssistantOrchestrator, get_assistant_orchestrator

router = APIRouter(tags=["assistant"])


@router.post("/assistant/chat")
async def assistant_chat(
    body: AssistantChatRequest,
    request: Request,
    orchestrator: AssistantOrchestrator = Depends(get_assistant_orchestrator),
) -> StreamingResponse:
    client_ip = _client_ip(request)

    async def event_stream() -> AsyncIterator[str]:
        async for event in orchestrator.handle(body, client_ip):
            yield sse_payload(event)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
