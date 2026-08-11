# AI Weather Assistant — Design Spec

**Date:** 2026-08-11  
**Status:** Draft — pending review

## Goal

Add a natural-language AI weather assistant to Local Rain that answers questions using **actual radar/nearest-rain data** from the existing backend — never inventing observations.

## Current Architecture (as-is)

```
Browser (Nuxt 4 + Vue 3 + MapLibre)
  ↓ REST
FastAPI (apps/api)
  ↓
Services: RadarService, NearestRainService, CloudsService, GeocodingService
  ↓
External: RainViewer (radar), NASA GIBS Himawari (clouds), Nominatim (geocode)
```

- **No LLM today** — advice is deterministic rules (`advice_rules.py`)
- **No rain cell IDs** — vectors identified by lat/lng
- **No NWP forecast API** — only RainViewer nowcast frames + motion extrapolation
- **Redis cache** for radar/nearest-rain; Postgres models empty

## Proposed Architecture

```
Frontend Chat UI
  ↓ POST /api/assistant/chat (SSE stream)
AssistantService (orchestrator)
  ↓ function calling
WeatherToolLayer (wraps existing services, no duplicate logic)
  ↓
NearestRainService | RadarService | CloudsService | GeocodingService
  ↓
Gemini API (google-genai) — server-side only
```

### Session context (from frontend)

```typescript
{
  latitude: number
  longitude: number
  lang: "vi" | "en"
  selectedCell?: { latitude, longitude }  // nearest rain or user tap
  radarTimestamp?: string
  viewport?: { north, south, east, west, zoom }
}
```

### Conversation

- Client sends bounded history (last N turns, e.g. 10)
- Server validates + truncates again before Gemini call
- System instruction enforces OBSERVATION / INFERENCE / UNCERTAINTY framing

### Structured actions (SSE events)

```json
{ "type": "status", "message": "Checking latest radar..." }
{ "type": "text_delta", "content": "..." }
{ "type": "action", "action": "highlight_rain_cell", "latitude": 10.5, "longitude": 106.2 }
{ "type": "weather_facts", "facts": { "distance": 8400, "direction": "NE", ... } }
{ "type": "done" }
{ "type": "error", "code": "radar_unavailable", "message": "..." }
```

Highlight uses **coordinates**, not parsed NL — cell IDs deferred to v2 (see Limitations).

## Tools — Implemented vs Deferred

| Tool | Status | Data source |
|------|--------|-------------|
| `get_nearest_rain` | ✅ Implement | `NearestRainService.find_nearest()` |
| `get_rain_vectors` | ✅ Implement | `NearestRainService.find_vectors()` |
| `get_radar_state` | ✅ Implement | `RadarService.get_radar_frames()` |
| `get_location_label` | ✅ Implement | `GeocodingService` |
| `get_sky_state` | ✅ Implement | cloud sample via nearest-rain path |
| `get_rain_cells` | ⚠️ Partial | rain-vectors clusters; no persistent cell_id |
| `get_rain_cell_details` | ⚠️ Partial | lookup by lat/lng within tolerance |
| `get_rain_movement` | ⚠️ Partial | motion from nearest-rain / vector item |
| `get_current_weather` | ❌ Skip | no temp/humidity/wind datasource |
| `get_weather_forecast` | ❌ Skip | no NWP; only RainViewer nowcast metadata |

## System Instruction (summary)

- Weather analyst persona, friendly Vietnamese/English matching user language
- Must cite Local Rain data; distinguish observation vs extrapolation
- Never claim certainty beyond data
- Concise unless user asks for detail
- When data unavailable: say so, do not guess

## Frontend UX

- Floating **"Ask Local Rain AI"** button (desktop + mobile)
- Bottom-sheet chat panel reusing `BottomSheet` patterns + Tailwind tokens
- Quick-question chips (i18n keys in `vi.json` / `en.json`)
- Streaming text + status line
- Map highlight via existing `MapView` rain marker + optional `flyToStreetView`
- Does not replace radar UI — overlay only

## Security & Cost

- `GEMINI_API_KEY`, `GEMINI_MODEL` server env only
- Rate limit: Redis sliding window per IP (e.g. 20 req / 5 min)
- Input validation: lat/lng bounds, message length cap (2000 chars)
- Compact tool JSON only — no raw tile bytes to Gemini
- Logging: request id, tools called, durations, token usage — no raw coords in logs (rounded)

## Error Handling

| Condition | Behavior |
|-----------|----------|
| Gemini down | SSE error event, retry button |
| Radar unavailable | Tool returns error; assistant explains limitation |
| No rain cells | Valid empty result |
| No location | Prompt user to enable GPS or pin location |
| Rate limit | 429 with friendly message |

## Testing

- pytest suite (new) with mocked Gemini + mocked services
- Tests: tool schemas, chat endpoint, streaming, invalid inputs, no radar, rate limit

## Known Limitations (v1)

1. No stable rain cell IDs — highlight by lat/lng
2. No multi-day forecast
3. No temperature/wind/humidity
4. Drizzle (<35 dBZ) filtered from map detection
5. ETA capped at 90 minutes
6. Conversation not persisted server-side (client history only)

## Files to Create

**Backend**
- `apps/api/app/routers/assistant.py`
- `apps/api/app/schemas/assistant.py`
- `apps/api/app/services/assistant/gemini_client.py`
- `apps/api/app/services/assistant/orchestrator.py`
- `apps/api/app/services/assistant/system_prompt.py`
- `apps/api/app/services/assistant/tools.py`
- `apps/api/app/services/assistant/rate_limit.py`
- `apps/api/tests/` (pytest setup + test files)

**Frontend**
- `apps/web/components/assistant/AssistantFab.vue`
- `apps/web/components/assistant/AssistantChat.vue`
- `apps/web/components/assistant/AssistantMessage.vue`
- `apps/web/components/assistant/WeatherFactsCard.vue`
- `apps/web/composables/useAssistant.ts`
- `apps/web/types/assistant.ts`

**Shared**
- Extend `packages/shared/src/index.ts` with assistant types

## Files to Modify

- `apps/api/app/main.py` — register assistant router
- `apps/api/app/core/config.py` — Gemini settings
- `apps/api/pyproject.toml` — google-genai, pytest
- `.env.example` — GEMINI_* vars
- `apps/web/pages/index.vue` — FAB + chat + map highlight wiring
- `apps/web/components/map/MapView.vue` — optional highlight prop
- `apps/web/i18n/locales/{vi,en}.json` — assistant strings

## Risks

| Risk | Mitigation |
|------|------------|
| Gemini hallucination | Tool-first architecture + strict system prompt |
| Vercel cold start + long radar scan | Reuse Redis cache; status SSE early |
| Token cost | Compact tools, bounded history, fast model default |
| No pytest baseline | Add minimal pytest infra in same PR |
| Cell selection ambiguous | Pass explicit session context from frontend |
