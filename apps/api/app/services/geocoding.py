from __future__ import annotations

from app.core.config import get_settings
from app.core.http_client import get_http_client


class GeocodingService:
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

    async def reverse_geocode(self, latitude: float, longitude: float) -> str:
        settings = get_settings()
        headers = {
            "User-Agent": f"{settings.app_name}/{settings.app_version} (local-rain)",
            "Accept-Language": "en",
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
                self.NOMINATIM_URL, params=params, headers=headers, timeout=5.0
            )
            response.raise_for_status()
            payload = response.json()
        except Exception:
            return self._fallback_label(latitude, longitude)

        return self._format_label(payload) or self._fallback_label(latitude, longitude)

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
                city = address.get("city") or address.get("town") or address.get("state")
                if city and city != value:
                    return f"{value}"
                return value.strip()

        display_name = payload.get("display_name")
        if isinstance(display_name, str) and display_name.strip():
            return display_name.split(",")[0].strip()
        return None

    def _fallback_label(self, latitude: float, longitude: float) -> str:
        return f"{latitude:.4f}, {longitude:.4f}"


def get_geocoding_service() -> GeocodingService:
    return GeocodingService()
