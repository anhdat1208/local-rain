from __future__ import annotations

import json
import time
from typing import Any

from app.core.redis import get_redis

GRID_DEG = 0.03
STATIONARY_SECONDS = 2 * 60 * 60
MIN_TRACK_DBZ = 35.0
CELL_KEY_PREFIX = "clutter:cell:v1:"
ACTIVE_SET_KEY = "clutter:active:v1"
TRACK_TTL_SECONDS = 7 * 24 * 60 * 60
# In-process cache so tile filters do not SMEMBERS on every pixel pass
_ACTIVE_CACHE: tuple[float, frozenset[tuple[int, int]]] | None = None
_ACTIVE_CACHE_TTL_S = 60.0


def cell_index(lat: float, lon: float) -> tuple[int, int]:
    return int(round(lat / GRID_DEG)), int(round(lon / GRID_DEG))


def cell_label(iy: int, ix: int) -> str:
    return f"{iy}:{ix}"


def parse_cell_label(label: str) -> tuple[int, int] | None:
    try:
        iy_s, ix_s = label.split(":", 1)
        return int(iy_s), int(ix_s)
    except (TypeError, ValueError):
        return None


class ClutterTracker:
    """Persist nearly-stationary high-dBZ cells and expose a clutter mask."""

    def __init__(self, redis: Any | None = None) -> None:
        self._redis = redis

    def _client(self) -> Any:
        return self._redis if self._redis is not None else get_redis()

    def observe_field(
        self,
        field: dict[tuple[int, int], float],
        *,
        moving: bool,
        now: int | None = None,
        history_credit_s: int = 0,
        clear_missing: bool = False,
        previous_keys: set[tuple[int, int]] | None = None,
    ) -> None:
        """Update tracks for hot cells. Fail-open on Redis errors."""
        ts = int(now if now is not None else time.time())
        try:
            redis = self._client()
            hot = {
                key: dbz
                for key, dbz in field.items()
                if dbz >= MIN_TRACK_DBZ
            }
            if clear_missing and previous_keys:
                for key in previous_keys - hot.keys():
                    self._clear_cell(redis, key)

            for key, dbz in hot.items():
                if moving:
                    self._clear_cell(redis, key)
                    continue
                self._touch_stationary(
                    redis,
                    key,
                    dbz=dbz,
                    now=ts,
                    history_credit_s=history_credit_s,
                )
            self._invalidate_active_cache()
        except Exception:
            return

    def is_clutter(self, lat: float, lon: float, now: int | None = None) -> bool:
        return self.is_clutter_cell(*cell_index(lat, lon), now=now)

    def is_clutter_cell(
        self, iy: int, ix: int, now: int | None = None
    ) -> bool:
        ts = int(now if now is not None else time.time())
        try:
            raw = self._client().get(f"{CELL_KEY_PREFIX}{iy}:{ix}")
            if not raw:
                return False
            data = json.loads(raw)
            stationary_since = int(data.get("stationary_since") or 0)
            last_hot = int(data.get("last_hot") or 0)
            if stationary_since <= 0:
                return False
            # Stale track with no recent echo should not suppress forever mid-request
            if ts - last_hot > STATIONARY_SECONDS:
                return False
            return ts - stationary_since >= STATIONARY_SECONDS
        except Exception:
            return False

    def active_cells(self) -> set[tuple[int, int]]:
        global _ACTIVE_CACHE
        now = time.time()
        if _ACTIVE_CACHE is not None and now - _ACTIVE_CACHE[0] < _ACTIVE_CACHE_TTL_S:
            return set(_ACTIVE_CACHE[1])
        try:
            members = self._client().smembers(ACTIVE_SET_KEY) or set()
            cells: set[tuple[int, int]] = set()
            for member in members:
                parsed = parse_cell_label(str(member))
                if parsed is not None:
                    cells.add(parsed)
            _ACTIVE_CACHE = (now, frozenset(cells))
            return cells
        except Exception:
            return set()

    def _touch_stationary(
        self,
        redis: Any,
        key: tuple[int, int],
        *,
        dbz: float,
        now: int,
        history_credit_s: int,
    ) -> None:
        iy, ix = key
        redis_key = f"{CELL_KEY_PREFIX}{iy}:{ix}"
        label = cell_label(iy, ix)
        raw = redis.get(redis_key)
        credit = max(0, int(history_credit_s))
        if raw:
            data = json.loads(raw)
            stationary_since = int(data.get("stationary_since") or now)
        else:
            stationary_since = now - credit
        payload = {
            "stationary_since": stationary_since,
            "last_hot": now,
            "peak_dbz": round(float(dbz), 1),
        }
        redis.setex(redis_key, TRACK_TTL_SECONDS, json.dumps(payload))
        if now - stationary_since >= STATIONARY_SECONDS:
            redis.sadd(ACTIVE_SET_KEY, label)
            try:
                redis.expire(ACTIVE_SET_KEY, TRACK_TTL_SECONDS)
            except Exception:
                pass
        else:
            redis.srem(ACTIVE_SET_KEY, label)

    def _clear_cell(self, redis: Any, key: tuple[int, int]) -> None:
        iy, ix = key
        redis.delete(f"{CELL_KEY_PREFIX}{iy}:{ix}")
        redis.srem(ACTIVE_SET_KEY, cell_label(iy, ix))

    @staticmethod
    def _invalidate_active_cache() -> None:
        global _ACTIVE_CACHE
        _ACTIVE_CACHE = None


def get_clutter_tracker() -> ClutterTracker:
    return ClutterTracker()
