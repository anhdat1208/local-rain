from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """Process-wide HTTP client with connection pooling (RainViewer / GIBS / Nominatim)."""
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            timeout=httpx.Timeout(16.0, connect=5.0),
            limits=httpx.Limits(max_connections=64, max_keepalive_connections=32),
            follow_redirects=True,
            headers={"User-Agent": "local-rain-api/1.0"},
        )
    return _client


async def close_http_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
