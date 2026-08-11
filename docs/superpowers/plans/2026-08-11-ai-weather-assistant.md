# AI Weather Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable natural-language weather Q&A grounded in Local Rain radar/nearest-rain data via Gemini function calling and a streaming chat UI.

**Architecture:** FastAPI assistant router → orchestrator with google-genai function calling → thin tool layer wrapping existing services → SSE to Nuxt chat UI with map highlight actions.

**Tech Stack:** Python 3.13, FastAPI, google-genai, Redis rate limit, Nuxt 4, Vue 3, TypeScript, pytest

## Global Constraints

- Never expose `GEMINI_API_KEY` to frontend
- Never invent weather data — tools only return real service output
- Do not duplicate radar/nearest-rain logic — wrap existing services
- Model via `GEMINI_MODEL` env var (default: `gemini-2.0-flash`)
- Preserve all existing radar/map/nearest-rain functionality
- Bilingual VI/EN matching user language
- Streaming SSE for chat responses

---

### Task 1: Backend config & dependencies

**Files:**
- Modify: `apps/api/pyproject.toml`
- Modify: `apps/api/app/core/config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `Settings.gemini_api_key: str | None`, `Settings.gemini_model: str`

- [ ] **Step 1:** Add `google-genai>=1.0.0` and `pytest`, `pytest-asyncio`, `httpx` to pyproject.toml dev/test deps
- [ ] **Step 2:** Add config fields with defaults
- [ ] **Step 3:** Document env vars in `.env.example`

```python
# config.py additions
gemini_api_key: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")
gemini_model: str = Field(default="gemini-2.0-flash", validation_alias="GEMINI_MODEL")
assistant_rate_limit: int = Field(default=20, validation_alias="ASSISTANT_RATE_LIMIT")
assistant_rate_window_seconds: int = Field(default=300, validation_alias="ASSISTANT_RATE_WINDOW")
```

---

### Task 2: Weather tool layer

**Files:**
- Create: `apps/api/app/services/assistant/tools.py`
- Create: `apps/api/app/services/assistant/tool_schemas.py`

**Interfaces:**
- Consumes: `NearestRainService`, `RadarService`, `CloudsService`, `GeocodingService`
- Produces: `WeatherTools.execute(name, args) -> dict`, `TOOL_DECLARATIONS` for Gemini

Tools to implement:
1. `get_nearest_rain(lat, lng, lang?)`
2. `get_rain_vectors(lat, lng, radius_km?, limit?)`
3. `get_radar_state()`
4. `get_location_label(lat, lng)`

- [ ] **Step 1:** Write failing tests in `apps/api/tests/test_assistant_tools.py`
- [ ] **Step 2:** Implement tool wrappers calling existing services (mock in tests)
- [ ] **Step 3:** Return compact JSON summaries (strip verbose fields)

---

### Task 3: Gemini client & system prompt

**Files:**
- Create: `apps/api/app/services/assistant/gemini_client.py`
- Create: `apps/api/app/services/assistant/system_prompt.py`

**Interfaces:**
- Produces: `GeminiAssistantClient.chat_stream(messages, tools, context) -> AsyncIterator[events]`

- [ ] **Step 1:** System prompt with OBSERVATION/INFERENCE/UNCERTAINTY rules (VI/EN)
- [ ] **Step 2:** Gemini client with function calling loop (max 5 tool rounds)
- [ ] **Step 3:** Mock Gemini in tests — verify tool call dispatch

---

### Task 4: Orchestrator & rate limiting

**Files:**
- Create: `apps/api/app/services/assistant/orchestrator.py`
- Create: `apps/api/app/services/assistant/rate_limit.py`
- Create: `apps/api/app/schemas/assistant.py`

**Interfaces:**
- Produces: `AssistantOrchestrator.handle(request, client_ip) -> AsyncIterator[SSEEvent]`

Request schema:
```python
class AssistantChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    context: SessionContext
```

- [ ] **Step 1:** Redis sliding-window rate limiter
- [ ] **Step 2:** Orchestrator merges session context into first user turn
- [ ] **Step 3:** Emit structured actions when tool returns rain coordinates

---

### Task 5: Assistant API endpoint (SSE)

**Files:**
- Create: `apps/api/app/routers/assistant.py`
- Modify: `apps/api/app/main.py`

**Interfaces:**
- Produces: `POST /api/assistant/chat` → `text/event-stream`

- [ ] **Step 1:** SSE endpoint with `EventSourceResponse`
- [ ] **Step 2:** Register router in main.py
- [ ] **Step 3:** Integration tests with TestClient + mocked Gemini

---

### Task 6: Shared types

**Files:**
- Modify: `packages/shared/src/index.ts`
- Create: `apps/web/types/assistant.ts`

Types: `AssistantChatRequest`, `AssistantSSEEvent`, `WeatherFacts`, `HighlightRainCellAction`

---

### Task 7: Frontend composable & streaming

**Files:**
- Create: `apps/web/composables/useAssistant.ts`

- [ ] **Step 1:** `sendMessage()` using `fetch` + ReadableStream SSE parser
- [ ] **Step 2:** Manage messages, loading, error, retry state
- [ ] **Step 3:** Pass location/radar context from Pinia stores

---

### Task 8: Chat UI components

**Files:**
- Create: `apps/web/components/assistant/AssistantFab.vue`
- Create: `apps/web/components/assistant/AssistantChat.vue`
- Create: `apps/web/components/assistant/AssistantMessage.vue`
- Create: `apps/web/components/assistant/WeatherFactsCard.vue`
- Modify: `apps/web/i18n/locales/vi.json`, `en.json`

UX:
- FAB bottom-right
- Chat in bottom sheet (reuse BottomSheet or nested panel)
- Quick question chips
- Clear conversation button

---

### Task 9: Map integration

**Files:**
- Modify: `apps/web/pages/index.vue`
- Modify: `apps/web/components/map/MapView.vue` (minimal — highlight prop)

- [ ] **Step 1:** On `highlight_rain_cell` action → set highlight coords + flyTo
- [ ] **Step 2:** Clear highlight when chat closes or new question

---

### Task 10: Error handling & observability

**Files:**
- Modify: orchestrator + router

- [ ] **Step 1:** Structured logging (request_id, tool, duration_ms)
- [ ] **Step 2:** Graceful degradation when GEMINI_API_KEY missing → 503 with clear message
- [ ] **Step 3:** Timeout wrapper (60s max on Vercel)

---

### Task 11: Test suite

**Files:**
- Create: `apps/api/tests/conftest.py`
- Create: `apps/api/tests/test_assistant_chat.py`
- Create: `apps/api/tests/test_assistant_tools.py`
- Create: `apps/api/tests/test_rate_limit.py`

Cases:
- Valid chat with mocked tool + Gemini
- Invalid lat/lng
- Missing API key
- No radar frames
- Rate limit exceeded
- Invalid cell lookup (lat/lng not found)

Run: `cd apps/api && pytest -v`

---

### Task 12: Production cleanup

- [ ] Update README section for assistant env vars
- [ ] Verify existing e2e scripts still pass
- [ ] Manual smoke test: VI question about nearest rain + follow-up "bao lâu nữa?"

---

## Environment Variables (new)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes (prod) | — | Google AI API key |
| `GEMINI_MODEL` | No | `gemini-2.0-flash` | Model name |
| `ASSISTANT_RATE_LIMIT` | No | `20` | Max requests per window |
| `ASSISTANT_RATE_WINDOW` | No | `300` | Window seconds |

## API Endpoints (new)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/assistant/chat` | SSE streaming chat |

## How to Run Locally

```bash
# .env
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-2.0-flash

docker compose up   # or run api + web separately
# Web: http://localhost:3000
# API docs: http://localhost:8000/docs
```

## How to Deploy

- Add `GEMINI_API_KEY` to Vercel env for API project
- Ensure Redis/KV available for rate limiting
- Web on Vercel: no new public env vars needed
