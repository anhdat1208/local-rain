from __future__ import annotations

import logging
import math
from typing import Any

from app.schemas.nearest_rain import NearestRainResponse, RainVectorItem
from app.services.clouds import CloudsService
from app.services.geocoding import GeocodingService
from app.services.nearest_rain import NearestRainService
from app.services.radar import RadarService

logger = logging.getLogger(__name__)


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def _compact_nearest(payload: NearestRainResponse) -> dict[str, Any]:
    trend: str | None = None
    if payload.previous_distance is not None and payload.distance >= 0:
        if payload.distance < payload.previous_distance - 500:
            trend = "approaching"
        elif payload.distance > payload.previous_distance + 500:
            trend = "moving_away"
        else:
            trend = "stable"

    return {
        "hasRain": payload.has_rain,
        "distanceM": payload.distance,
        "direction": payload.direction,
        "etaMinutes": payload.eta if payload.eta > 0 else None,
        "motionDirection": payload.motion_direction,
        "speedKmh": payload.speed_kmh if payload.speed_kmh > 0 else None,
        "approaching": payload.approaching,
        "previousDistanceM": payload.previous_distance,
        "trend": trend,
        "confidence": payload.confidence,
        "rainingHere": payload.raining_here,
        "rainChance": payload.rain_chance,
        "rainChancePct": payload.rain_chance_pct,
        "rainIn1h": payload.rain_in_1h,
        "rainIn2h": payload.rain_in_2h,
        "skyState": payload.sky_state,
        "cloudCoverPct": payload.cloud_cover_pct,
        "radarTimestamp": payload.radar_timestamp,
        "radarAgeMinutes": payload.radar_age_minutes,
        "rainLatitude": payload.rain_latitude,
        "rainLongitude": payload.rain_longitude,
        "explanation": payload.explanation,
        "advice": payload.advice,
        "limitations": [
            "Reflectivity only — no mm/h rainfall amount.",
            "Weak drizzle below ~35 dBZ may be missed.",
            "ETA extrapolation capped at 90 minutes.",
        ],
    }


def _compact_vector(item: RainVectorItem, ref_lat: float, ref_lon: float) -> dict[str, Any]:
    return {
        "latitude": item.latitude,
        "longitude": item.longitude,
        "toLatitude": item.to_latitude,
        "toLongitude": item.to_longitude,
        "speedKmh": item.speed_kmh,
        "direction": item.direction,
        "dbz": item.dbz,
        "distanceFromRefM": round(_haversine_m(ref_lat, ref_lon, item.latitude, item.longitude)),
    }


class WeatherTools:
    def __init__(
        self,
        nearest_rain: NearestRainService | None = None,
        radar: RadarService | None = None,
        geocoding: GeocodingService | None = None,
    ) -> None:
        self._nearest = nearest_rain or NearestRainService(RadarService())
        self._radar = radar or RadarService()
        self._geocoding = geocoding or GeocodingService()

    async def execute(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        try:
            if name == "get_nearest_rain":
                return await self._get_nearest_rain(args)
            if name == "get_rain_vectors":
                return await self._get_rain_vectors(args)
            if name == "get_radar_state":
                return await self._get_radar_state()
            if name == "get_location_label":
                return await self._get_location_label(args)
            if name == "get_rain_cell_near":
                return await self._get_rain_cell_near(args)
            return {"error": "unknown_tool", "message": f"Unknown tool: {name}"}
        except Exception as exc:
            logger.exception("assistant tool %s failed", name)
            return {"error": "tool_failed", "message": str(exc)}

    async def _get_nearest_rain(self, args: dict[str, Any]) -> dict[str, Any]:
        lat = float(args["latitude"])
        lng = float(args["longitude"])
        lang = str(args.get("lang") or "vi")
        result = await self._nearest.find_nearest(lat, lng, lang=lang)
        if not result.radar_timestamp and result.distance < 0:
            return {"error": "radar_unavailable", "message": "Radar frames unavailable."}
        return {"ok": True, "data": _compact_nearest(result)}

    async def _get_rain_vectors(self, args: dict[str, Any]) -> dict[str, Any]:
        lat = float(args["latitude"])
        lng = float(args["longitude"])
        radius = float(args.get("radius_km") or 100)
        limit = int(args.get("limit") or 8)
        result = await self._nearest.find_vectors(lat, lng, radius_km=radius, limit=limit)
        return {
            "ok": True,
            "count": len(result.vectors),
            "generatedAt": result.generated_at,
            "vectors": [_compact_vector(v, lat, lng) for v in result.vectors],
        }

    async def _get_radar_state(self) -> dict[str, Any]:
        frames = await self._radar.get_radar_frames()
        if not frames.frames:
            return {"error": "radar_unavailable", "message": "No radar frames."}
        unix_times = [f.unix_time for f in frames.frames]
        latest = max(unix_times)
        return {
            "ok": True,
            "frameCount": len(frames.frames),
            "latestUnixTime": latest,
            "latestTimestamp": next(
                (f.timestamp for f in frames.frames if f.unix_time == latest),
                None,
            ),
            "generatedAt": frames.generated_at,
            "host": frames.host,
        }

    async def _get_location_label(self, args: dict[str, Any]) -> dict[str, Any]:
        lat = float(args["latitude"])
        lng = float(args["longitude"])
        label = await self._geocoding.reverse_geocode(lat, lng)
        return {"ok": True, "label": label, "latitude": lat, "longitude": lng}

    async def _get_rain_cell_near(self, args: dict[str, Any]) -> dict[str, Any]:
        lat = float(args["latitude"])
        lng = float(args["longitude"])
        radius = float(args.get("search_radius_km") or 15)
        vectors = await self._nearest.find_vectors(lat, lng, radius_km=max(radius, 20), limit=16)
        if not vectors.vectors:
            return {"ok": True, "found": False, "message": "No rain cells in search area."}

        best: RainVectorItem | None = None
        best_dist = float("inf")
        for item in vectors.vectors:
            dist = _haversine_m(lat, lng, item.latitude, item.longitude)
            if dist < best_dist:
                best_dist = dist
                best = item

        if best is None:
            return {"ok": True, "found": False}

        tolerance_m = max(5_000.0, radius * 1000)
        if best_dist > tolerance_m:
            return {
                "ok": True,
                "found": False,
                "message": f"No cell within {int(tolerance_m / 1000)} km of target.",
                "nearestDistanceM": round(best_dist),
            }

        return {
            "ok": True,
            "found": True,
            "distanceFromTargetM": round(best_dist),
            "cell": _compact_vector(best, lat, lng),
        }


def get_weather_tools() -> WeatherTools:
    return WeatherTools()
