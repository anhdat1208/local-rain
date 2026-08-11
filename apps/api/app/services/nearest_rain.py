from __future__ import annotations

import asyncio
import contextvars
import io
import json
import math
import time
from datetime import UTC, datetime
from dataclasses import dataclass

import httpx
from PIL import Image

from app.core.http_client import get_http_client
from app.core.redis import get_redis
from app.schemas.nearest_rain import NearestRainResponse, RainVectorItem, RainVectorsResponse
from app.schemas.radar import RadarFrameSchema
from app.services.advice_rules import (
    Lang,
    build_advice,
    is_raining_here,
    normalize_lang,
)
from app.services.clouds import CloudCoverSample, CloudsService
from app.services.radar import RadarService
from app.services.radar_dbz import (
    MAX_DBZ,
    pixel_dbz,
)
from app.utils.geo import (
    CompassDirection,
    bearing_deg,
    compass_from_bearing,
    haversine_m,
    latlon_to_tile,
    tile_pixel_to_latlon,
)

RADAR_ZOOM = 7
TILE_SIZE = 256
MAX_TILE_RADIUS = 3
PIXEL_STEP = 2
CACHE_TTL_SECONDS = 120
MIN_CLOSING_MPS = 0.9
MAX_ETA_MINUTES = 90
# Rain counts as "arrived" once the cell centre is this close
HIT_RADIUS_M = 3_000.0
# Beyond this, a hit is too far to call "nearby rain" in the card
MAX_NEARBY_M = 120_000.0
# Window used to describe where the cell was a moment ago
PREVIOUS_WINDOW_S = 600.0
VELOCITY_RADIUS_M = 100_000.0
# Each +1 dBZ is worth this many meters when choosing between fringe vs core.
# Keep small: at z7 (~1.2 km/px) proximity must dominate or we lock onto a far core.
CORE_DBZ_METERS = 120.0
VECTOR_TILE_RADIUS = 1
# Detection is stricter than the map filter for far cores, but keeps a soft local path
# so thin real showers within a few km are not discarded for a stronger cell farther away.
DETECT_MIN_DBZ = 35.0
DETECT_MIN_SUPPORT = 4
DETECT_SUPPORT_RADIUS_PX = 4  # Chebyshev window ≈ 2.4 km at z7
LOCAL_SOFT_DBZ = 25.0  # advice-only: catch light returns without painting them on the map
# Isolated speckle is clutter, so a soft hit must sit inside a small cluster
LOCAL_MIN_SUPPORT = 3
# Soft path reaches farther so leftover showers aren't ignored for a distant core
LOCAL_RADIUS_M = 6_000.0
# Motion grid: ~3.3 km cells
MOTION_GRID_DEG = 0.03
MOTION_LOCAL_SPAN = 2
MOTION_MAX_KEYS = 1200
MOTION_MAX_SEARCH_CELLS = 12
# Storm-scale advection tops out well below this; anything faster is correlation noise
MOTION_MAX_SPEED_KMH = 70.0
MOTION_MIN_SPEED_KMH = 3.0
# The correlation peak must beat "no movement" by this much to be trusted
MOTION_MIN_PEAK_GAIN = 1.06
# Repeated mosaics: accept a past frame only once ~15% of the echo field changed
MOTION_CHANGE_RATIO = 0.85
MOTION_MAX_LOOKBACK_S = 5400
MOTION_MAX_FRAME_TRIES = 5
MOTION_BASELINES = 3
# Each arrow covers a ~10 km cluster (3x3 motion cells)
VECTOR_CLUSTER_CELLS = 3
VECTOR_MIN_CLUSTER_CELLS = 2
VECTOR_CLUSTER_WINDOW = 6
VECTOR_MIN_SEPARATION_M = 12_000.0
# dBZ traded per km of distance: rain over your head matters more than a far core
VECTOR_DISTANCE_PENALTY = 0.25
# Arrows show where a cell is heading over this horizon
VECTOR_PROJECT_MINUTES = 30.0
VECTOR_MIN_LENGTH_M = 6_000.0
VECTOR_MAX_LENGTH_M = 40_000.0
# Strong bias so a solid nearby echo beats a far core of similar strength
NEAR_CORE_BONUS_M = 6_000.0
NEAR_CORE_RADIUS_M = 5_000.0
MID_CORE_BONUS_M = 2_500.0
MID_CORE_RADIUS_M = 8_000.0

# Request-scoped PNG bytes so hit-scan + motion share the same RainViewer GETs
_tile_bytes_var: contextvars.ContextVar[dict[str, bytes | None] | None] = contextvars.ContextVar(
    "nearest_tile_bytes", default=None
)
_MOTION_LOCAL_MAX = 48


@dataclass(slots=True)
class RainHit:
    latitude: float
    longitude: float
    distance_m: float
    intensity: float
    dbz: float = 0.0
    # Sampled neighbours inside the support window; small values mean speckle
    support: int = 0


@dataclass(slots=True)
class RainCluster:
    latitude: float
    longitude: float
    dbz: float
    pixels: int
    distance_m: float


@dataclass(slots=True)
class MotionContext:
    current_field: dict[tuple[int, int], float]
    baselines: list[tuple[RadarFrameSchema, dict[tuple[int, int], float]]]
    velocity: tuple[float, float] | None


# Singleflight motion across /nearest-rain + /rain-vectors cold stampede
_motion_inflight: dict[str, asyncio.Task[MotionContext]] = {}
_motion_local: dict[str, MotionContext] = {}


@dataclass(slots=True)
class CachedVelocity:
    velocity: tuple[float, float] | None


@dataclass(slots=True)
class MotionEstimate:
    motion_direction: CompassDirection | None
    speed_kmh: float
    approaching: bool
    eta_minutes: int
    previous_distance_m: float | None
    closing_mps: float


class NearestRainService:
    def __init__(
        self,
        radar_service: RadarService,
        clouds_service: CloudsService | None = None,
    ) -> None:
        self._radar_service = radar_service
        self._clouds_service = clouds_service or CloudsService()

    async def find_nearest(
        self,
        latitude: float,
        longitude: float,
        lang: str | None = "vi",
    ) -> NearestRainResponse:
        locale = normalize_lang(lang)
        frames = await self._radar_service.get_radar_frames()
        if not frames.frames:
            msg = (
                "Không lấy được khung radar."
                if locale == "vi"
                else "Radar frames unavailable."
            )
            return self._empty_result(msg, locale)

        current = self._pick_current_frame(frames.frames)
        cache_key = (
            f"nearest-rain:v20:{locale}:{current.unix_time}:"
            f"{round(latitude, 3)}:{round(longitude, 3)}"
        )
        cached = self._read_cache(cache_key)
        if cached is not None:
            return self._with_fresh_age(cached, current)

        tile_token = _tile_bytes_var.set({})
        try:
            client = get_http_client()
            current_upstream = await self._radar_service.upstream_for_frame(current.unix_time)
            # Same velocity field that drives the map arrows, so both stay consistent
            current_hit, motion_ctx, clouds = await asyncio.gather(
                self._find_nearest_hit(
                    client=client,
                    tile_url_template=current_upstream,
                    ref_lat=latitude,
                    ref_lon=longitude,
                    max_radius=MAX_TILE_RADIUS,
                ),
                self._shared_motion_context(
                    client=client,
                    frames=frames.frames,
                    current=current,
                    latitude=latitude,
                    longitude=longitude,
                    radius_m=VELOCITY_RADIUS_M,
                ),
                self._clouds_service.sample_cover(latitude, longitude),
            )
            velocity = motion_ctx.velocity
        finally:
            _tile_bytes_var.reset(tile_token)

        if current_hit is not None and current_hit.distance_m > MAX_NEARBY_M:
            current_hit = None

        motion = self._motion_from_velocity(
            user_lat=latitude,
            user_lon=longitude,
            hit=current_hit,
            velocity=velocity,
        )
        result = self._build_response(
            latitude, longitude, current_hit, motion, locale, current, clouds
        )
        # Always cache radar answer. Short TTL if cloud sample missed so we don't
        # lock a false "clear sky" badge for the full 2 minutes.
        ttl = CACHE_TTL_SECONDS if clouds.ok else 25
        self._write_cache(cache_key, result, ttl)
        return result

    async def find_vectors(
        self,
        latitude: float,
        longitude: float,
        radius_km: float = 100,
        limit: int = 8,
    ) -> RainVectorsResponse:
        frames = await self._radar_service.get_radar_frames()
        if not frames.frames:
            return RainVectorsResponse(vectors=[], generated_at=datetime.now(tz=UTC).isoformat())

        current = self._pick_current_frame(frames.frames)

        radius_m = max(20_000.0, min(200_000.0, radius_km * 1000.0))
        cache_key = (
            f"rain-vectors:v5:{current.unix_time}:"
            f"{round(latitude, 3)}:{round(longitude, 3)}:{int(radius_m)}:{limit}"
        )
        cached = self._read_vectors_cache(cache_key)
        if cached is not None:
            return cached

        tile_token = _tile_bytes_var.set({})
        try:
            client = get_http_client()
            context = await self._shared_motion_context(
                client=client,
                frames=frames.frames,
                current=current,
                latitude=latitude,
                longitude=longitude,
                radius_m=radius_m,
            )
        finally:
            _tile_bytes_var.reset(tile_token)

        global_velocity = context.velocity
        if global_velocity is None or not context.baselines:
            return self._empty_vectors()

        current_field = context.current_field
        clusters = self._clusters_from_field(current_field, latitude, longitude, radius_m)
        if not clusters:
            return self._empty_vectors()

        # Cluster refinement runs against the most recent frame that actually changed
        reference_frame, reference_field = context.baselines[0]
        reference_dt = max(1, current.unix_time - reference_frame.unix_time)
        base_cells = (
            int(round(global_velocity[0] * reference_dt / MOTION_GRID_DEG)),
            int(round(global_velocity[1] * reference_dt / MOTION_GRID_DEG)),
        )

        vectors: list[RainVectorItem] = []
        for cluster in self._spread_clusters(clusters, limit):
            local = self._estimate_velocity(
                current_field=current_field,
                previous_field=reference_field,
                keys=self._cluster_keys(current_field, cluster),
                dt=reference_dt,
                user_lat=latitude,
                base=base_cells,
                span=MOTION_LOCAL_SPAN,
            )
            velocity = local or global_velocity
            vector = self._build_vector(cluster, velocity, latitude)
            if vector is not None:
                vectors.append(vector)

        response = RainVectorsResponse(
            vectors=vectors[:limit],
            generated_at=datetime.now(tz=UTC).isoformat(),
        )
        self._write_vectors_cache(cache_key, response)
        return response

    def _empty_vectors(self) -> RainVectorsResponse:
        return RainVectorsResponse(vectors=[], generated_at=datetime.now(tz=UTC).isoformat())

    async def _shared_motion_context(
        self,
        client: httpx.AsyncClient,
        frames: list[RadarFrameSchema],
        current: RadarFrameSchema,
        latitude: float,
        longitude: float,
        radius_m: float,
    ) -> MotionContext:
        """Deduplicate motion work when nearest-rain and rain-vectors fire together."""
        key = (
            f"{self._velocity_cache_key(current, latitude, longitude)}:{int(radius_m)}"
        )
        local = _motion_local.get(key)
        if local is not None:
            return local

        existing = _motion_inflight.get(key)
        if existing is not None:
            return await existing

        async def run() -> MotionContext:
            try:
                ctx = await self._motion_context(
                    client=client,
                    frames=frames,
                    current=current,
                    latitude=latitude,
                    longitude=longitude,
                    radius_m=radius_m,
                )
                _motion_local[key] = ctx
                while len(_motion_local) > _MOTION_LOCAL_MAX:
                    _motion_local.pop(next(iter(_motion_local)))
                return ctx
            finally:
                _motion_inflight.pop(key, None)

        task = asyncio.create_task(run())
        _motion_inflight[key] = task
        return await task

    async def _motion_context(
        self,
        client: httpx.AsyncClient,
        frames: list[RadarFrameSchema],
        current: RadarFrameSchema,
        latitude: float,
        longitude: float,
        radius_m: float,
    ) -> MotionContext:
        upstream = await self._radar_service.upstream_for_frame(current.unix_time)
        current_field = await self._collect_field(
            client=client,
            tile_url_template=upstream,
            user_lat=latitude,
            user_lon=longitude,
            radius_m=radius_m,
        )
        if not current_field:
            return MotionContext(current_field={}, baselines=[], velocity=None)

        baselines = await self._collect_baselines(
            client=client,
            frames=frames,
            current=current,
            current_field=current_field,
            user_lat=latitude,
            user_lon=longitude,
            radius_m=radius_m * 1.35,
        )
        keys = sorted(current_field, key=lambda key: current_field[key], reverse=True)[
            :MOTION_MAX_KEYS
        ]
        velocities = [
            velocity
            for frame, field in baselines
            if (
                velocity := self._estimate_velocity(
                    current_field=current_field,
                    previous_field=field,
                    keys=keys,
                    dt=max(1, current.unix_time - frame.unix_time),
                    user_lat=latitude,
                    base=(0, 0),
                    span=None,
                )
            )
            is not None
        ]
        velocity = self._median_velocity(velocities)
        self._write_velocity_cache(
            self._velocity_cache_key(current, latitude, longitude), velocity
        )
        return MotionContext(
            current_field=current_field,
            baselines=baselines,
            velocity=velocity,
        )

    async def _regional_velocity(
        self,
        client: httpx.AsyncClient,
        frames: list[RadarFrameSchema],
        current: RadarFrameSchema,
        latitude: float,
        longitude: float,
    ) -> tuple[float, float] | None:
        key = self._velocity_cache_key(current, latitude, longitude)
        cached = self._read_velocity_cache(key)
        if cached is not None:
            return cached.velocity

        context = await self._shared_motion_context(
            client=client,
            frames=frames,
            current=current,
            latitude=latitude,
            longitude=longitude,
            radius_m=VELOCITY_RADIUS_M,
        )
        return context.velocity

    def _velocity_cache_key(
        self,
        current: RadarFrameSchema,
        latitude: float,
        longitude: float,
    ) -> str:
        # Advection is a regional property, so neighbours can share one estimate
        return (
            f"rain-velocity:v3:{current.unix_time}:"
            f"{round(latitude, 1)}:{round(longitude, 1)}"
        )

    def _motion_from_velocity(
        self,
        user_lat: float,
        user_lon: float,
        hit: RainHit | None,
        velocity: tuple[float, float] | None,
    ) -> MotionEstimate:
        empty = MotionEstimate(
            motion_direction=None,
            speed_kmh=0.0,
            approaching=False,
            eta_minutes=0,
            previous_distance_m=None,
            closing_mps=0.0,
        )
        if hit is None or velocity is None:
            return empty

        lon_m_per_deg = 111_320.0 * math.cos(math.radians(user_lat))
        east_mps = velocity[1] * lon_m_per_deg
        north_mps = velocity[0] * 111_320.0
        speed_mps = math.hypot(east_mps, north_mps)
        if speed_mps <= 0:
            return empty

        # Cell position relative to the user, in metres
        east_m = (hit.longitude - user_lon) * lon_m_per_deg
        north_m = (hit.latitude - user_lat) * 111_320.0
        distance_m = math.hypot(east_m, north_m) or hit.distance_m
        closing_mps = -(east_m * east_mps + north_m * north_mps) / max(distance_m, 1.0)

        approaching = False
        eta_minutes = 0
        if closing_mps >= MIN_CLOSING_MPS:
            seconds = self._time_to_reach(east_m, north_m, east_mps, north_mps, HIT_RADIUS_M)
            if seconds is not None:
                # Already inside the arrival radius and still closing: treat as imminent
                minutes = max(1, int(round(seconds / 60.0)))
                if minutes <= MAX_ETA_MINUTES:
                    approaching = True
                    eta_minutes = minutes

        previous_distance = math.hypot(
            east_m - east_mps * PREVIOUS_WINDOW_S,
            north_m - north_mps * PREVIOUS_WINDOW_S,
        )
        return MotionEstimate(
            motion_direction=compass_from_bearing(
                math.degrees(math.atan2(east_mps, north_mps)) % 360.0
            ),
            speed_kmh=round(speed_mps * 3.6, 1),
            approaching=approaching,
            eta_minutes=eta_minutes,
            previous_distance_m=round(previous_distance),
            closing_mps=closing_mps,
        )

    def _time_to_reach(
        self,
        east_m: float,
        north_m: float,
        east_mps: float,
        north_mps: float,
        radius_m: float,
    ) -> float | None:
        """Seconds until the cell centre comes within radius_m of the user."""
        a = east_mps**2 + north_mps**2
        if a <= 0:
            return None
        c = east_m**2 + north_m**2 - radius_m**2
        if c <= 0:
            return 0.0
        b = 2 * (east_m * east_mps + north_m * north_mps)
        discriminant = b**2 - 4 * a * c
        if discriminant < 0:
            return None
        root = math.sqrt(discriminant)
        times = [t for t in ((-b - root) / (2 * a), (-b + root) / (2 * a)) if t > 0]
        return min(times) if times else None

    async def _collect_baselines(
        self,
        client: httpx.AsyncClient,
        frames: list[RadarFrameSchema],
        current: RadarFrameSchema,
        current_field: dict[tuple[int, int], float],
        user_lat: float,
        user_lon: float,
        radius_m: float,
    ) -> list[tuple[RadarFrameSchema, dict[tuple[int, int], float]]]:
        """RainViewer repeats identical mosaics over this region, so keep walking back
        until the echo field really changed — identical frames imply zero motion."""
        self_score = sum(dbz - DETECT_MIN_DBZ + 1.0 for dbz in current_field.values())
        if self_score <= 0:
            return []

        older = [
            frame
            for frame in frames
            if frame.unix_time < current.unix_time
            and current.unix_time - frame.unix_time <= MOTION_MAX_LOOKBACK_S
        ]
        older.sort(key=lambda frame: frame.unix_time, reverse=True)

        baselines: list[tuple[RadarFrameSchema, dict[tuple[int, int], float]]] = []
        # Prefetch several past frames in parallel, then pick ones that actually changed
        candidates = older[:MOTION_MAX_FRAME_TRIES]
        if not candidates:
            return []

        async def load_frame(
            frame: RadarFrameSchema,
        ) -> tuple[RadarFrameSchema, dict[tuple[int, int], float]] | None:
            upstream = await self._radar_service.upstream_for_frame(frame.unix_time)
            field = await self._collect_field(
                client=client,
                tile_url_template=upstream,
                user_lat=user_lat,
                user_lon=user_lon,
                radius_m=radius_m,
            )
            if not field:
                return None
            return frame, field

        loaded = await asyncio.gather(*(load_frame(frame) for frame in candidates))
        for item in loaded:
            if item is None:
                continue
            frame, field = item
            unchanged = sum(
                min(dbz, field[key]) - DETECT_MIN_DBZ + 1.0
                for key, dbz in current_field.items()
                if key in field
            )
            if unchanged > self_score * MOTION_CHANGE_RATIO:
                continue
            baselines.append((frame, field))
            if len(baselines) >= MOTION_BASELINES:
                break
        return baselines

    def _estimate_velocity(
        self,
        current_field: dict[tuple[int, int], float],
        previous_field: dict[tuple[int, int], float],
        keys: list[tuple[int, int]],
        dt: int,
        user_lat: float,
        base: tuple[int, int],
        span: int | None,
    ) -> tuple[float, float] | None:
        """Velocity in degrees/second, or None when the correlation peak is not trustworthy."""
        if not keys or not previous_field:
            return None

        cell_lat_m = MOTION_GRID_DEG * 111_320.0
        cell_lon_m = MOTION_GRID_DEG * 111_320.0 * math.cos(math.radians(user_lat))
        max_move_m = MOTION_MAX_SPEED_KMH / 3.6 * dt
        span_y = span if span is not None else int(max_move_m // max(cell_lat_m, 1.0))
        span_x = span if span is not None else int(max_move_m // max(cell_lon_m, 1.0))
        span_y = max(1, min(MOTION_MAX_SEARCH_CELLS, span_y))
        span_x = max(1, min(MOTION_MAX_SEARCH_CELLS, span_x))

        candidates: list[tuple[int, int]] = []
        for shift_y in range(base[0] - span_y, base[0] + span_y + 1):
            for shift_x in range(base[1] - span_x, base[1] + span_x + 1):
                moved_m = math.hypot(shift_y * cell_lat_m, shift_x * cell_lon_m)
                if moved_m > max_move_m:
                    continue
                candidates.append((shift_y, shift_x))

        scores = self._correlate(current_field, previous_field, keys, candidates)
        if not scores:
            return None

        best_score = max(scores.values())
        if base == (0, 0):
            stationary = scores.get((0, 0), 0.0)
            if best_score < stationary * MOTION_MIN_PEAK_GAIN:
                return None

        plausible = [shift for shift, score in scores.items() if score >= best_score * 0.995]
        plausible.sort(
            key=lambda shift: (
                abs(shift[0] - base[0]) + abs(shift[1] - base[1]),
                -scores[shift],
            )
        )
        peak = plausible[0]
        shift_y = peak[0] + self._subcell_offset(scores, peak, axis=0)
        shift_x = peak[1] + self._subcell_offset(scores, peak, axis=1)

        moved_m = math.hypot(shift_y * cell_lat_m, shift_x * cell_lon_m)
        speed_kmh = moved_m / dt * 3.6
        if speed_kmh < MOTION_MIN_SPEED_KMH or speed_kmh > MOTION_MAX_SPEED_KMH:
            return None
        return (shift_y * MOTION_GRID_DEG / dt, shift_x * MOTION_GRID_DEG / dt)

    def _correlate(
        self,
        current_field: dict[tuple[int, int], float],
        previous_field: dict[tuple[int, int], float],
        keys: list[tuple[int, int]],
        candidates: list[tuple[int, int]],
    ) -> dict[tuple[int, int], float]:
        scores: dict[tuple[int, int], float] = {}
        for shift_y, shift_x in candidates:
            score = 0.0
            for key in keys:
                previous_dbz = previous_field.get((key[0] - shift_y, key[1] - shift_x))
                if previous_dbz is None:
                    continue
                score += min(current_field[key], previous_dbz) - DETECT_MIN_DBZ + 1.0
            if score > 0:
                scores[(shift_y, shift_x)] = score
        return scores

    def _median_velocity(self, velocities: list[tuple[float, float]]) -> tuple[float, float] | None:
        if not velocities:
            return None
        lats = sorted(item[0] for item in velocities)
        lons = sorted(item[1] for item in velocities)
        mid = len(velocities) // 2
        return (lats[mid], lons[mid])

    def _spread_clusters(self, clusters: list[RainCluster], limit: int) -> list[RainCluster]:
        """Keep the strongest cells but spread them out, favouring nearby rain."""
        ranked = sorted(
            clusters,
            key=lambda cell: cell.dbz - cell.distance_m / 1000.0 * VECTOR_DISTANCE_PENALTY,
            reverse=True,
        )
        picked: list[RainCluster] = []
        for cluster in ranked:
            too_close = any(
                haversine_m(cluster.latitude, cluster.longitude, other.latitude, other.longitude)
                < VECTOR_MIN_SEPARATION_M
                for other in picked
            )
            if too_close:
                continue
            picked.append(cluster)
            if len(picked) >= limit:
                break
        return picked

    def _cluster_keys(
        self,
        field: dict[tuple[int, int], float],
        cluster: RainCluster,
    ) -> list[tuple[int, int]]:
        center_y = int(round(cluster.latitude / MOTION_GRID_DEG))
        center_x = int(round(cluster.longitude / MOTION_GRID_DEG))
        keys: list[tuple[int, int]] = []
        for dy in range(-VECTOR_CLUSTER_WINDOW, VECTOR_CLUSTER_WINDOW + 1):
            for dx in range(-VECTOR_CLUSTER_WINDOW, VECTOR_CLUSTER_WINDOW + 1):
                key = (center_y + dy, center_x + dx)
                if key in field:
                    keys.append(key)
        return keys

    def _subcell_offset(
        self,
        scores: dict[tuple[int, int], float],
        peak: tuple[int, int],
        axis: int,
    ) -> float:
        """Parabolic fit around the correlation peak; the grid alone is too coarse."""
        lower = (peak[0] - 1, peak[1]) if axis == 0 else (peak[0], peak[1] - 1)
        upper = (peak[0] + 1, peak[1]) if axis == 0 else (peak[0], peak[1] + 1)
        left = scores.get(lower)
        right = scores.get(upper)
        center = scores[peak]
        if left is None or right is None:
            return 0.0
        denominator = left - 2 * center + right
        if denominator == 0:
            return 0.0
        offset = 0.5 * (left - right) / denominator
        return max(-0.5, min(0.5, offset))

    def _build_vector(
        self,
        cluster: RainCluster,
        velocity: tuple[float, float],
        user_lat: float,
    ) -> RainVectorItem | None:
        """Project a cell forward along its velocity (degrees/second)."""
        lat_per_s, lon_per_s = velocity
        speed_ms = math.hypot(
            lat_per_s * 111_320.0,
            lon_per_s * 111_320.0 * math.cos(math.radians(user_lat)),
        )
        speed_kmh = speed_ms * 3.6
        if speed_kmh < MOTION_MIN_SPEED_KMH:
            return None

        # Stretch the arrow to the projection horizon so it stays readable on the map
        horizon_m = speed_ms * VECTOR_PROJECT_MINUTES * 60.0
        length_m = max(VECTOR_MIN_LENGTH_M, min(VECTOR_MAX_LENGTH_M, horizon_m))
        seconds = length_m / speed_ms
        target_lat = cluster.latitude + lat_per_s * seconds
        target_lon = cluster.longitude + lon_per_s * seconds
        bearing = bearing_deg(cluster.latitude, cluster.longitude, target_lat, target_lon)
        return RainVectorItem(
            latitude=round(cluster.latitude, 5),
            longitude=round(cluster.longitude, 5),
            to_latitude=round(target_lat, 5),
            to_longitude=round(target_lon, 5),
            speed_kmh=round(speed_kmh, 1),
            direction=compass_from_bearing(bearing),
            dbz=round(cluster.dbz, 1),
        )

    def _pick_current_frame(self, frames: list[RadarFrameSchema]) -> RadarFrameSchema:
        now_sec = int(time.time())
        current = frames[0]
        for frame in frames:
            if frame.unix_time <= now_sec:
                current = frame
            else:
                break
        return current

    async def _find_nearest_hit(
        self,
        client: httpx.AsyncClient,
        tile_url_template: str,
        ref_lat: float,
        ref_lon: float,
        max_radius: int,
    ) -> RainHit | None:
        origin_tile_x, origin_tile_y = latlon_to_tile(ref_lat, ref_lon, RADAR_ZOOM)
        # Fetch all rings in one wave — same scoring as sequential rings, less wall time
        tiles: list[tuple[int, int]] = []
        for radius in range(0, max_radius + 1):
            tiles.extend(self._tiles_for_ring(origin_tile_x, origin_tile_y, radius))

        hits = await asyncio.gather(
            *(
                self._scan_tile(
                    client=client,
                    tile_url_template=tile_url_template,
                    tile_x=tile_x,
                    tile_y=tile_y,
                    ref_lat=ref_lat,
                    ref_lon=ref_lon,
                )
                for tile_x, tile_y in tiles
            )
        )
        best: RainHit | None = None
        for hit in hits:
            if hit is None:
                continue
            if self._is_better_hit(hit, best):
                best = hit
        return best

    def _tiles_for_ring(self, origin_x: int, origin_y: int, radius: int) -> list[tuple[int, int]]:
        n = 2**RADAR_ZOOM
        if radius == 0:
            return [(origin_x % n, origin_y)]

        coords: list[tuple[int, int]] = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if max(abs(dx), abs(dy)) != radius:
                    continue
                x = (origin_x + dx) % n
                y = origin_y + dy
                if y < 0 or y >= n:
                    continue
                coords.append((x, y))
        return coords

    def _approx_tile_width_m(self, latitude: float) -> float:
        meters_per_degree = 111_320 * math.cos(math.radians(latitude))
        degrees_per_tile = 360.0 / (2**RADAR_ZOOM)
        return abs(meters_per_degree * degrees_per_tile)

    async def _collect_field(
        self,
        client: httpx.AsyncClient,
        tile_url_template: str,
        user_lat: float,
        user_lon: float,
        radius_m: float,
    ) -> dict[tuple[int, int], float]:
        """Rasterise rain pixels into a sparse dBZ grid keyed by motion cell."""
        origin_tile_x, origin_tile_y = latlon_to_tile(user_lat, user_lon, RADAR_ZOOM)
        max_lat_delta = radius_m / 111_320.0
        max_lon_delta = radius_m / max(111_320.0 * math.cos(math.radians(user_lat)), 1.0)

        tiles: list[tuple[int, int]] = []
        for radius in range(0, VECTOR_TILE_RADIUS + 1):
            tiles.extend(self._tiles_for_ring(origin_tile_x, origin_tile_y, radius))

        images = await asyncio.gather(
            *(
                self._fetch_tile_image(client, tile_url_template, tile_x, tile_y)
                for tile_x, tile_y in tiles
            )
        )

        field: dict[tuple[int, int], float] = {}
        for (tile_x, tile_y), image in zip(tiles, images, strict=True):
            if image is None:
                continue
            self._accumulate_tile_field(
                image=image,
                tile_x=tile_x,
                tile_y=tile_y,
                user_lat=user_lat,
                user_lon=user_lon,
                max_lat_delta=max_lat_delta,
                max_lon_delta=max_lon_delta,
                field=field,
            )
        return field

    async def _fetch_tile_image(
        self,
        client: httpx.AsyncClient,
        tile_url_template: str,
        tile_x: int,
        tile_y: int,
    ) -> Image.Image | None:
        raw = await self._fetch_tile_bytes(client, tile_url_template, tile_x, tile_y)
        if raw is None:
            return None
        try:
            return Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            return None

    async def _fetch_tile_bytes(
        self,
        client: httpx.AsyncClient,
        tile_url_template: str,
        tile_x: int,
        tile_y: int,
    ) -> bytes | None:
        url = self._analysis_tile_url(tile_url_template, tile_x, tile_y)
        cache = _tile_bytes_var.get()
        if cache is not None and url in cache:
            return cache[url]

        content: bytes | None = None
        try:
            response = await client.get(url, timeout=12.0)
            if response.status_code == 200 and response.content:
                content = response.content
        except Exception:
            content = None

        if cache is not None:
            cache[url] = content
        return content

    def _accumulate_tile_field(
        self,
        image: Image.Image,
        tile_x: int,
        tile_y: int,
        user_lat: float,
        user_lon: float,
        max_lat_delta: float,
        max_lon_delta: float,
        field: dict[tuple[int, int], float],
    ) -> None:
        pixels = image.load()
        width, height = image.size
        for py in range(0, height, PIXEL_STEP):
            for px in range(0, width, PIXEL_STEP):
                r, g, b, a = pixels[px, py]
                dbz = pixel_dbz(r, g, b, a)
                if dbz < DETECT_MIN_DBZ:
                    continue
                lat, lon = tile_pixel_to_latlon(
                    tile_x,
                    tile_y,
                    RADAR_ZOOM,
                    px + 0.5,
                    py + 0.5,
                    TILE_SIZE,
                )
                if abs(lat - user_lat) > max_lat_delta or abs(lon - user_lon) > max_lon_delta:
                    continue
                key = (
                    int(round(lat / MOTION_GRID_DEG)),
                    int(round(lon / MOTION_GRID_DEG)),
                )
                if dbz > field.get(key, 0.0):
                    field[key] = dbz

    def _clusters_from_field(
        self,
        field: dict[tuple[int, int], float],
        user_lat: float,
        user_lon: float,
        radius_m: float,
    ) -> list[RainCluster]:
        """Merge motion cells into ~10 km clusters, one arrow per cluster."""
        buckets: dict[tuple[int, int], list[float]] = {}
        for (cell_y, cell_x), dbz in field.items():
            key = (cell_y // VECTOR_CLUSTER_CELLS, cell_x // VECTOR_CLUSTER_CELLS)
            weight = dbz - DETECT_MIN_DBZ + 1.0
            bucket = buckets.get(key)
            lat = cell_y * MOTION_GRID_DEG
            lon = cell_x * MOTION_GRID_DEG
            if bucket is None:
                buckets[key] = [lat * weight, lon * weight, weight, dbz, 1.0]
            else:
                bucket[0] += lat * weight
                bucket[1] += lon * weight
                bucket[2] += weight
                bucket[3] = max(bucket[3], dbz)
                bucket[4] += 1.0

        clusters: list[RainCluster] = []
        for lat_weighted, lon_weighted, weight_sum, max_dbz, cell_count in buckets.values():
            if cell_count < VECTOR_MIN_CLUSTER_CELLS or weight_sum <= 0:
                continue
            lat = lat_weighted / weight_sum
            lon = lon_weighted / weight_sum
            distance = haversine_m(user_lat, user_lon, lat, lon)
            if distance > radius_m:
                continue
            clusters.append(
                RainCluster(
                    latitude=lat,
                    longitude=lon,
                    dbz=max_dbz,
                    pixels=int(cell_count),
                    distance_m=distance,
                )
            )
        return clusters

    async def _scan_tile(
        self,
        client: httpx.AsyncClient,
        tile_url_template: str,
        tile_x: int,
        tile_y: int,
        ref_lat: float,
        ref_lon: float,
    ) -> RainHit | None:
        raw = await self._fetch_tile_bytes(client, tile_url_template, tile_x, tile_y)
        if raw is None:
            return None
        try:
            image = Image.open(io.BytesIO(raw)).convert("RGBA")
        except Exception:
            return None

        pixels = image.load()
        width, height = image.size
        # Soft pool (≥30) supports local detection; hard pool (≥35) for storm cores.
        soft: list[tuple[int, int, float, float, float]] = []
        hard: list[tuple[int, int, float, float, float]] = []

        for py in range(0, height, PIXEL_STEP):
            for px in range(0, width, PIXEL_STEP):
                r, g, b, a = pixels[px, py]
                dbz = pixel_dbz(r, g, b, a)
                if dbz < LOCAL_SOFT_DBZ:
                    continue
                rain_lat, rain_lon = tile_pixel_to_latlon(
                    tile_x,
                    tile_y,
                    RADAR_ZOOM,
                    px + 0.5,
                    py + 0.5,
                    TILE_SIZE,
                )
                item = (px, py, dbz, rain_lat, rain_lon)
                soft.append(item)
                if dbz >= DETECT_MIN_DBZ:
                    hard.append(item)

        best: RainHit | None = None
        radius = DETECT_SUPPORT_RADIUS_PX

        def consider(
            pool: list[tuple[int, int, float, float, float]],
            min_support: int,
            max_distance_m: float | None,
        ) -> None:
            nonlocal best
            if len(pool) < min_support:
                return
            # Grid lookup keeps the neighbour count O(window) instead of O(pool)
            occupied = {(px, py) for px, py, _, _, _ in pool}
            for px, py, dbz, rain_lat, rain_lon in pool:
                support = 0
                for oy in range(py - radius, py + radius + 1, PIXEL_STEP):
                    for ox in range(px - radius, px + radius + 1, PIXEL_STEP):
                        if (ox, oy) in occupied:
                            support += 1
                if support < min_support:
                    continue
                distance = haversine_m(ref_lat, ref_lon, rain_lat, rain_lon)
                if max_distance_m is not None and distance > max_distance_m:
                    continue
                intensity = max(
                    0.0,
                    min(1.0, (dbz - LOCAL_SOFT_DBZ) / (MAX_DBZ - LOCAL_SOFT_DBZ)),
                )
                candidate = RainHit(
                    latitude=rain_lat,
                    longitude=rain_lon,
                    distance_m=distance,
                    intensity=intensity,
                    dbz=dbz,
                    support=support,
                )
                if self._is_better_hit(candidate, best):
                    best = candidate

        consider(hard, DETECT_MIN_SUPPORT, None)
        consider(soft, LOCAL_MIN_SUPPORT, LOCAL_RADIUS_M)
        return best

    def _analysis_tile_url(self, tile_url_template: str, tile_x: int, tile_y: int) -> str:
        return (
            tile_url_template.replace("{z}", str(RADAR_ZOOM))
            .replace("{x}", str(tile_x))
            .replace("{y}", str(tile_y))
        )

    def _hit_score(self, hit: RainHit) -> float:
        # Lower is better. At mosaic zoom, prefer the closest real echo over a far hot core.
        strength = max(0.0, hit.dbz - DETECT_MIN_DBZ)
        score = hit.distance_m - CORE_DBZ_METERS * strength
        if hit.distance_m <= NEAR_CORE_RADIUS_M:
            score -= NEAR_CORE_BONUS_M
        elif hit.distance_m <= MID_CORE_RADIUS_M:
            score -= MID_CORE_BONUS_M
        return score

    def _is_better_hit(self, candidate: RainHit, best: RainHit | None) -> bool:
        if best is None:
            return True
        cand_score = self._hit_score(candidate)
        best_score = self._hit_score(best)
        if abs(cand_score - best_score) < 1.0:
            if candidate.dbz != best.dbz:
                return candidate.dbz > best.dbz
            return candidate.distance_m < best.distance_m
        return cand_score < best_score

    def _build_response(
        self,
        user_lat: float,
        user_lon: float,
        hit: RainHit | None,
        motion: MotionEstimate,
        lang: Lang,
        frame: RadarFrameSchema | None = None,
        clouds: CloudCoverSample | None = None,
    ) -> NearestRainResponse:
        radar_timestamp, radar_age = self._frame_age(frame)
        cloud_cover = (
            clouds.cover
            if clouds is not None and clouds.ok
            else None
        )
        cloud_pct = (
            int(round(max(0.0, min(1.0, cloud_cover)) * 100))
            if cloud_cover is not None
            else 0
        )
        if hit is None:
            msg = (
                "Không phát hiện mưa gần đây."
                if lang == "vi"
                else "No rain detected nearby."
            )
            return self._empty_result(
                msg, lang, radar_timestamp, radar_age, cloud_cover=cloud_cover
            )

        distance = int(round(hit.distance_m))
        direction = compass_from_bearing(
            bearing_deg(user_lat, user_lon, hit.latitude, hit.longitude)
        )
        # Confidence tracks reflectivity strength + motion corroboration
        confidence = int(
            min(
                92,
                max(
                    40,
                    round(30 + hit.intensity * 55 + (hit.dbz - DETECT_MIN_DBZ) * 0.4),
                ),
            )
        )
        if motion.approaching and motion.eta_minutes > 0:
            confidence = min(95, confidence + 6)

        copy = build_advice(
            has_rain=True,
            distance_m=distance,
            direction=direction,
            approaching=motion.approaching,
            eta_minutes=motion.eta_minutes,
            motion_direction=motion.motion_direction,
            speed_kmh=motion.speed_kmh,
            previous_distance_m=motion.previous_distance_m,
            lang=lang,
            intensity=hit.intensity,
            dbz=hit.dbz,
            support=hit.support,
            cloud_cover=cloud_cover,
        )

        return NearestRainResponse(
            distance=distance,
            eta=motion.eta_minutes,
            direction=direction,
            confidence=confidence,
            explanation=copy.explanation,
            advice=copy.advice,
            has_rain=True,
            rain_latitude=round(hit.latitude, 5),
            rain_longitude=round(hit.longitude, 5),
            motion_direction=motion.motion_direction,
            speed_kmh=motion.speed_kmh,
            approaching=motion.approaching,
            previous_distance=motion.previous_distance_m,
            rain_chance=copy.rain_chance,
            rain_chance_pct=copy.rain_chance_pct,
            rain_in_1h=copy.rain_in_1h,
            rain_in_2h=copy.rain_in_2h,
            raining_here=is_raining_here(distance, hit.dbz, hit.support),
            radar_timestamp=radar_timestamp,
            radar_age_minutes=radar_age,
            sky_state=copy.sky_state,
            cloud_cover_pct=cloud_pct,
        )

    def _frame_age(self, frame: RadarFrameSchema | None) -> tuple[str | None, int]:
        if frame is None:
            return None, 0
        age_s = max(0, int(time.time()) - int(frame.unix_time))
        return frame.timestamp, age_s // 60

    def _with_fresh_age(
        self, result: NearestRainResponse, frame: RadarFrameSchema
    ) -> NearestRainResponse:
        timestamp, age = self._frame_age(frame)
        return result.model_copy(
            update={"radar_timestamp": timestamp, "radar_age_minutes": age}
        )

    def _empty_result(
        self,
        explanation: str,
        lang: Lang = "vi",
        radar_timestamp: str | None = None,
        radar_age_minutes: int = 0,
        cloud_cover: float | None = None,
    ) -> NearestRainResponse:
        copy = build_advice(
            has_rain=False,
            distance_m=-1,
            direction="N",
            approaching=False,
            eta_minutes=0,
            motion_direction=None,
            speed_kmh=0,
            previous_distance_m=None,
            lang=lang,
            cloud_cover=cloud_cover,
        )
        # Prefer cloud-aware copy unless the caller forced a hard failure message
        use_explanation = explanation
        if explanation in {
            "Không phát hiện mưa gần đây.",
            "No rain detected nearby.",
        }:
            use_explanation = copy.explanation
        cloud_pct = (
            int(round(max(0.0, min(1.0, cloud_cover)) * 100))
            if cloud_cover is not None
            else 0
        )
        return NearestRainResponse(
            distance=-1,
            eta=0,
            direction="N",
            confidence=0,
            explanation=use_explanation or copy.explanation,
            advice=copy.advice,
            has_rain=False,
            rain_latitude=None,
            rain_longitude=None,
            motion_direction=None,
            speed_kmh=0,
            approaching=False,
            previous_distance=None,
            rain_chance=copy.rain_chance,
            rain_chance_pct=copy.rain_chance_pct,
            rain_in_1h=copy.rain_in_1h,
            rain_in_2h=copy.rain_in_2h,
            raining_here=False,
            radar_timestamp=radar_timestamp,
            radar_age_minutes=radar_age_minutes,
            sky_state=copy.sky_state,
            cloud_cover_pct=cloud_pct,
        )

    def _read_cache(self, key: str) -> NearestRainResponse | None:
        try:
            raw = get_redis().get(key)
        except Exception:
            return None
        if not raw:
            return None
        try:
            return NearestRainResponse.model_validate(json.loads(raw))
        except Exception:
            return None

    def _write_cache(
        self, key: str, payload: NearestRainResponse, ttl: int = CACHE_TTL_SECONDS
    ) -> None:
        try:
            get_redis().setex(key, max(5, ttl), payload.model_dump_json(by_alias=True))
        except Exception:
            return

    def _read_velocity_cache(self, key: str) -> CachedVelocity | None:
        try:
            raw = get_redis().get(key)
        except Exception:
            return None
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        if payload is None:
            return CachedVelocity(velocity=None)
        if isinstance(payload, list) and len(payload) == 2:
            return CachedVelocity(velocity=(float(payload[0]), float(payload[1])))
        return None

    def _write_velocity_cache(self, key: str, velocity: tuple[float, float] | None) -> None:
        try:
            get_redis().setex(
                key,
                CACHE_TTL_SECONDS,
                json.dumps(list(velocity) if velocity is not None else None),
            )
        except Exception:
            return

    def _read_vectors_cache(self, key: str) -> RainVectorsResponse | None:
        try:
            raw = get_redis().get(key)
        except Exception:
            return None
        if not raw:
            return None
        try:
            return RainVectorsResponse.model_validate(json.loads(raw))
        except Exception:
            return None

    def _write_vectors_cache(self, key: str, payload: RainVectorsResponse) -> None:
        try:
            get_redis().setex(key, CACHE_TTL_SECONDS, payload.model_dump_json(by_alias=True))
        except Exception:
            return


def get_nearest_rain_service() -> NearestRainService:
    return NearestRainService(RadarService())
