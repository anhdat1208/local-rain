from __future__ import annotations

import math
from typing import Literal

CompassDirection = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

_EARTH_RADIUS_M = 6_371_000.0
_DIRECTIONS: tuple[CompassDirection, ...] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_lambda = math.radians(lon2 - lon1)

    y = math.sin(d_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(d_lambda)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360.0) % 360.0


def compass_from_bearing(bearing: float) -> CompassDirection:
    index = int((bearing + 22.5) // 45) % 8
    return _DIRECTIONS[index]


def latlon_to_tile(lat: float, lon: float, zoom: int) -> tuple[int, int]:
    n = 2**zoom
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    x = min(max(x, 0), n - 1)
    y = min(max(y, 0), n - 1)
    return x, y


def tile_pixel_to_latlon(
    tile_x: int,
    tile_y: int,
    zoom: int,
    pixel_x: float,
    pixel_y: float,
    tile_size: int = 256,
) -> tuple[float, float]:
    n = 2**zoom
    lon = (tile_x + pixel_x / tile_size) / n * 360.0 - 180.0
    mercator_y = 1.0 - 2.0 * (tile_y + pixel_y / tile_size) / n
    lat = math.degrees(math.atan(math.sinh(math.pi * mercator_y)))
    return lat, lon
