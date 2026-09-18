from __future__ import annotations

from app.services.advice_rules import build_advice, normalize_lang


def test_stationary_clutter_advice_vi() -> None:
    copy = build_advice(
        has_rain=True,
        distance_m=1100,
        direction="SW",
        approaching=False,
        eta_minutes=0,
        motion_direction="SW",
        speed_kmh=0,
        previous_distance_m=None,
        lang="vi",
        intensity=0.9,
        dbz=55,
        support=20,
        stationary_clutter=True,
    )
    assert copy.rain_chance_pct <= 25
    assert "nhiễu" in copy.explanation.lower() or "echo giả" in copy.explanation.lower()
    assert "đang mưa tại chỗ" not in copy.explanation.lower()
    assert copy.sky_state != "raining"


def test_stationary_clutter_advice_en() -> None:
    copy = build_advice(
        has_rain=True,
        distance_m=500,
        direction="N",
        approaching=False,
        eta_minutes=0,
        motion_direction=None,
        speed_kmh=0,
        previous_distance_m=None,
        lang="en",
        intensity=0.8,
        dbz=50,
        support=15,
        stationary_clutter=True,
    )
    assert copy.rain_chance_pct <= 25
    assert "clutter" in copy.explanation.lower() or "false" in copy.explanation.lower()
    assert copy.sky_state != "raining"


def test_normalize_lang_default_vi() -> None:
    assert normalize_lang(None) == "vi"
