from __future__ import annotations

from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.http_client import get_http_client
from app.core.redis import get_redis

CACHE_TTL_SECONDS = 7 * 24 * 3600  # place names are stable
CACHE_PREFIX = "geocode:v2"


class GeocodingService:
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

    async def reverse_geocode(
        self, latitude: float, longitude: float, lang: str = "vi"
    ) -> str:
        locale = "vi" if lang.startswith("vi") else "en"
        cache_key = self._cache_key(latitude, longitude, locale)

        cached = self._read_cache(cache_key)
        if cached:
            return cached

        label = await self._fetch_nominatim(latitude, longitude, locale)
        if label and not self._is_coordinate_fallback(label):
            self._write_cache(cache_key, label)
            return label

        return self._fallback_label(latitude, longitude)

    async def _fetch_nominatim(
        self, latitude: float, longitude: float, locale: str
    ) -> str | None:
        settings = get_settings()
        headers = {
            "User-Agent": f"{settings.app_name}/{settings.app_version} (local-rain)",
            "Accept-Language": "vi,en" if locale == "vi" else "en",
        }
        params = {
            "lat": latitude,
            "lon": longitude,
            "format": "jsonv2",
            "zoom": 14,
            "addressdetails": 1,
        }

        try:
            client = get_http_client()
            response = await client.get(
                self.NOMINATIM_URL, params=params, headers=headers, timeout=4.0
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return None

        return self._format_label(payload)

    def _format_label(self, payload: dict) -> str | None:
        address = payload.get("address") or {}
        candidates = [
            address.get("suburb"),
            address.get("neighbourhood"),
            address.get("quarter"),
            address.get("city_district"),
            address.get("district"),
            address.get("town"),
            address.get("city"),
            address.get("village"),
            address.get("county"),
            address.get("state"),
        ]
        for value in candidates:
            if isinstance(value, str) and value.strip():
                return value.strip()

        display_name = payload.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.split(",")[0].strip()

        name = payload.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
        return None

    def _fallback_label(self, latitude: float, longitude: float) -> str:
        return f"{latitude:.4f}, {longitude:.4f}"

    @staticmethod
    def _is_coordinate_fallback(label: str) -> bool:
        # Matches "10.7729, 106.6927" style fallbacks — never cache these.
        parts = [p.strip() for p in label.split(",")]
        if len(parts) != 2:
            return False
        try:
            float(parts[0])
            float(parts[1])
            return True
        except ValueError:
            return False

    @staticmethod
    def _cache_key(latitude: float, longitude: float, locale: str) -> str:
        # ~110m grid — enough for neighborhood labels, good hit rate while walking
        return f"{CACHE_PREFIX}:{locale}:{round(latitude, 3)}:{round(longitude, 3)}"

    def _read_cache(self, key: str) -> str | None:
        try:
            value = get_redis().get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        except RedisError:
            return None
        return None

    def _write_cache(self, key: str, label: str) -> None:
        try:
            get_redis().setex(key, CACHE_TTL_SECONDS, label)
        except RedisError:
            return


def get_geocoding_service() -> GeocodingService:
    return GeocodingService()
