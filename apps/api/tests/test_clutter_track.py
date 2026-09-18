from __future__ import annotations

from unittest.mock import MagicMock

from app.services.clutter_track import (
    GRID_DEG,
    STATIONARY_SECONDS,
    ClutterTracker,
    cell_index,
)


def test_cell_index_matches_motion_grid() -> None:
    assert cell_index(10.745, 106.670) == (
        int(round(10.745 / GRID_DEG)),
        int(round(106.670 / GRID_DEG)),
    )


def test_observe_with_two_hour_credit_marks_clutter() -> None:
    store: dict[str, str] = {}
    active: set[str] = set()
    redis = _fake_redis(store, active)
    tracker = ClutterTracker(redis=redis)
    field = {cell_index(10.745, 106.670): 55.0}
    now = 1_700_000_000

    tracker.observe_field(field, moving=False, now=now, history_credit_s=STATIONARY_SECONDS)

    assert tracker.is_clutter(10.745, 106.670, now=now)
    assert cell_index(10.745, 106.670) in tracker.active_cells()


def test_fresh_stationary_without_credit_is_not_clutter_yet() -> None:
    store: dict[str, str] = {}
    active: set[str] = set()
    redis = _fake_redis(store, active)
    tracker = ClutterTracker(redis=redis)
    field = {cell_index(10.745, 106.670): 55.0}
    now = 1_700_000_000

    tracker.observe_field(field, moving=False, now=now, history_credit_s=0)

    assert not tracker.is_clutter(10.745, 106.670, now=now)


def test_motion_resets_clutter() -> None:
    store: dict[str, str] = {}
    active: set[str] = set()
    redis = _fake_redis(store, active)
    tracker = ClutterTracker(redis=redis)
    key = cell_index(10.745, 106.670)
    field = {key: 55.0}
    now = 1_700_000_000

    tracker.observe_field(field, moving=False, now=now, history_credit_s=STATIONARY_SECONDS)
    assert tracker.is_clutter(10.745, 106.670, now=now)

    tracker.observe_field(field, moving=True, now=now + 60, history_credit_s=0)
    assert not tracker.is_clutter(10.745, 106.670, now=now + 60)
    assert key not in tracker.active_cells()


def test_cold_cell_clears_active() -> None:
    store: dict[str, str] = {}
    active: set[str] = set()
    redis = _fake_redis(store, active)
    tracker = ClutterTracker(redis=redis)
    key = cell_index(10.745, 106.670)
    now = 1_700_000_000
    tracker.observe_field(
        {key: 55.0}, moving=False, now=now, history_credit_s=STATIONARY_SECONDS
    )
    tracker.observe_field(
        {},
        moving=False,
        now=now + 60,
        history_credit_s=0,
        clear_missing=True,
        previous_keys={key},
    )
    assert not tracker.is_clutter(10.745, 106.670, now=now + 60)


def test_redis_failure_fail_open() -> None:
    redis = MagicMock()
    redis.get.side_effect = RuntimeError("down")
    redis.smembers.side_effect = RuntimeError("down")
    tracker = ClutterTracker(redis=redis)
    tracker.observe_field({(1, 2): 50.0}, moving=False, now=1_700_000_000)
    assert not tracker.is_clutter(0.03, 0.06)


def _fake_redis(store: dict[str, str], active: set[str]) -> MagicMock:
    redis = MagicMock()

    def get(key: str):
        return store.get(key)

    def setex(key: str, _ttl: int, value: str):
        store[key] = value

    def delete(*keys: str):
        for key in keys:
            store.pop(key, None)

    def sadd(_key: str, member: str):
        active.add(member)

    def srem(_key: str, member: str):
        active.discard(member)

    def smembers(_key: str):
        return set(active)

    def expire(_key: str, _ttl: int):
        return True

    redis.get.side_effect = get
    redis.setex.side_effect = setex
    redis.delete.side_effect = delete
    redis.sadd.side_effect = sadd
    redis.srem.side_effect = srem
    redis.smembers.side_effect = smembers
    redis.expire.side_effect = expire
    return redis
