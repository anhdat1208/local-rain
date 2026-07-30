from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.utils.geo import CompassDirection

Lang = Literal["en", "vi"]
RainChance = Literal["none", "low", "medium", "high"]


@dataclass(frozen=True, slots=True)
class AdviceResult:
    explanation: str
    advice: str
    rain_chance: RainChance
    rain_chance_pct: int
    rain_in_1h: bool
    rain_in_2h: bool


# Band treated as "very close" when scoring chance
RAINING_HERE_M = 2_500
# A radar pixel spans ~1.2 km, so allow that much slop — but no more. Field reports
# show a cell 3–4 km away regularly leaves the user completely dry.
HERE_STRONG_M = 2_000
HERE_MODERATE_M = 1_500
HERE_WEAK_M = 800
# Below this the echo is often aloft only (virga) or plain clutter — no wet ground
CONFIRM_DBZ = 30.0
# At this strength the cell reliably reaches the ground as real rain
STRONG_DBZ = 35.0


# Sampled neighbours a cell must have before it counts as a real shower rather
# than mosaic speckle. The window holds 25 samples, so this is roughly 15 km².
SOLID_SUPPORT = 8


def is_raining_here(distance_m: int, dbz: float, support: int = 0) -> bool:
    """Rain over the user needs proximity, reflectivity and a solid cluster."""
    if support and support < SOLID_SUPPORT:
        # Isolated speckle: only trust it when it is practically overhead
        return dbz >= STRONG_DBZ and distance_m <= HERE_WEAK_M
    if dbz >= STRONG_DBZ:
        return distance_m <= HERE_STRONG_M
    if dbz >= CONFIRM_DBZ:
        return distance_m <= HERE_MODERATE_M
    # Weak returns only count when they sit almost exactly overhead
    return dbz > 0 and distance_m <= HERE_WEAK_M


_DIR_VI: dict[str, str] = {
    "N": "Bắc",
    "NE": "Đông Bắc",
    "E": "Đông",
    "SE": "Đông Nam",
    "S": "Nam",
    "SW": "Tây Nam",
    "W": "Tây",
    "NW": "Tây Bắc",
}


def normalize_lang(lang: str | None) -> Lang:
    if lang and lang.lower().startswith("en"):
        return "en"
    return "vi"


def _dir(direction: CompassDirection | str, lang: Lang) -> str:
    key = str(direction)
    if lang == "vi":
        return _DIR_VI.get(key, key)
    return key


def estimate_rain_chance(
    *,
    has_rain: bool,
    distance_m: int,
    approaching: bool,
    eta_minutes: int,
    intensity: float = 0.0,
    dbz: float = 0.0,
    support: int = 0,
) -> tuple[RainChance, int]:
    """Heuristic nowcast chance at the user's spot (not a NWP forecast)."""
    if not has_rain:
        return "none", 8

    score = 18.0
    if distance_m <= 250:
        score += 62
    elif distance_m <= RAINING_HERE_M:
        score += 52
    elif distance_m <= 4000:
        score += 28
    elif distance_m <= 10000:
        score += 16
    elif distance_m <= 20000:
        score += 8
    else:
        score += 3

    if approaching and eta_minutes > 0:
        if eta_minutes <= 8:
            score += 28
        elif eta_minutes <= 20:
            score += 18
        elif eta_minutes <= 45:
            score += 10
        else:
            score += 4
    elif approaching:
        score += 8

    score += max(0.0, min(14.0, intensity * 14.0))
    pct = int(max(5, min(92, round(score))))

    # A weak echo can never justify a near-certain call, however close it sits
    if dbz > 0:
        if dbz < CONFIRM_DBZ:
            pct = min(pct, 45)
        elif dbz < STRONG_DBZ:
            pct = min(pct, 70)
    # Speckle a few pixels wide is usually clutter, not a shower
    if support and support < SOLID_SUPPORT:
        pct = min(pct, 50)

    if pct >= 65:
        return "high", pct
    if pct >= 40:
        return "medium", pct
    return "low", pct


def _chance_line(chance: RainChance, pct: int, lang: Lang) -> str:
    if lang == "vi":
        labels = {
            "none": "rất thấp",
            "low": "thấp",
            "medium": "trung bình",
            "high": "cao",
        }
        return f"Khả năng mưa tại chỗ: {labels[chance]} (~{pct}%)."
    labels = {
        "none": "very low",
        "low": "low",
        "medium": "moderate",
        "high": "high",
    }
    return f"Rain chance at your spot: {labels[chance]} (~{pct}%)."


def _horizon_rain_flags(
    *,
    has_rain: bool,
    distance_m: int,
    approaching: bool,
    eta_minutes: int,
    pct: int,
    raining_here: bool = False,
    dbz: float = 0.0,
    support: int = 0,
) -> tuple[bool, bool]:
    if not has_rain:
        return False, False
    if raining_here:
        return True, True
    if support and support < SOLID_SUPPORT:
        # Clutter-sized echo: not a basis for forecasting rain over the next hours
        return False, pct >= 45
    if 0 < dbz < CONFIRM_DBZ:
        # Weak echo drifting over you rarely turns into rain on the ground
        return False, pct >= 40
    if approaching and eta_minutes > 0:
        return (eta_minutes <= 60, eta_minutes <= 120)
    in_1h = pct >= 45
    in_2h = pct >= 32
    return in_1h, in_2h


def build_advice(
    *,
    has_rain: bool,
    distance_m: int,
    direction: CompassDirection | str,
    approaching: bool,
    eta_minutes: int,
    motion_direction: CompassDirection | str | None,
    speed_kmh: float,
    previous_distance_m: float | None,
    lang: Lang = "vi",
    intensity: float = 0.0,
    dbz: float = 0.0,
    support: int = 0,
) -> AdviceResult:
    """Deterministic nowcast copy — no LLM."""
    chance, pct = estimate_rain_chance(
        has_rain=has_rain,
        distance_m=distance_m,
        approaching=approaching,
        eta_minutes=eta_minutes,
        intensity=intensity,
        dbz=dbz,
        support=support,
    )
    raining_here = has_rain and is_raining_here(distance_m, dbz, support)
    rain_in_1h, rain_in_2h = _horizon_rain_flags(
        has_rain=has_rain,
        distance_m=distance_m,
        approaching=approaching,
        eta_minutes=eta_minutes,
        pct=pct,
        raining_here=raining_here,
        dbz=dbz,
        support=support,
    )
    chance_bit = _chance_line(chance, pct, lang)

    if not has_rain:
        if lang == "vi":
            return AdviceResult(
                explanation="Radar không thấy ô mưa rõ gần đây.",
                advice=(
                    f"{chance_bit} Tạm ổn để ra ngoài, nhưng mưa phùn/mưa nhỏ "
                    "thường không lên radar — mang ô nếu trời còn ẩm."
                ),
                rain_chance=chance,
                rain_chance_pct=pct,
                rain_in_1h=rain_in_1h,
                rain_in_2h=rain_in_2h,
            )
        return AdviceResult(
            explanation="No clear rain cell nearby on radar.",
            advice=(
                f"{chance_bit} Mostly fine to go out, but light drizzle often "
                "does not show on radar — bring an umbrella if it still feels damp."
            ),
            rain_chance=chance,
            rain_chance_pct=pct,
            rain_in_1h=rain_in_1h,
            rain_in_2h=rain_in_2h,
        )

    distance_text = _format_distance(distance_m, lang)
    dir_text = _dir(direction, lang)
    motion_text = _dir(motion_direction, lang) if motion_direction else None
    moving_away = (
        previous_distance_m is not None
        and distance_m > previous_distance_m + 80
        and not approaching
    )

    def pack(explanation: str, advice: str) -> AdviceResult:
        return AdviceResult(
            explanation=explanation,
            advice=f"{chance_bit} {advice}",
            rain_chance=chance,
            rain_chance_pct=pct,
            rain_in_1h=rain_in_1h,
            rain_in_2h=rain_in_2h,
        )

    if raining_here:
        overhead = distance_m <= 800
        if lang == "vi":
            if overhead:
                explanation = "Đang mưa tại chỗ — ô mưa ngay trên đầu bạn."
            else:
                explanation = (
                    f"Đang mưa tại chỗ — tâm echo radar cách ~{distance_text} "
                    "(độ phân giải ~1 km, mưa có thể đang trên đầu dù tâm lệch)."
                )
            return pack(explanation, "Trú lại hoặc mang ô — mưa đang ở ngay đây.")
        if overhead:
            explanation = "Raining at your spot — the cell is right overhead."
        else:
            explanation = (
                f"Raining at your spot — radar cell centre ~{distance_text} away "
                "(~1 km resolution; rain can still be over you)."
            )
        return pack(explanation, "Stay covered or take an umbrella — rain is here now.")

    if support and support < SOLID_SUPPORT and distance_m <= 12_000:
        if lang == "vi":
            return pack(
                f"Chỉ là đốm echo nhỏ lẻ (~{dbz:.0f} dBZ, vài km²) cách {distance_text} "
                f"hướng {dir_text} — thường là nhiễu radar chứ không phải ô mưa.",
                "Nhiều khả năng trời vẫn ráo; không cần lo lắm.",
            )
        return pack(
            f"Just an isolated speck (~{dbz:.0f} dBZ, a few km²) {distance_text} "
            f"toward {direction} — usually radar clutter, not a shower.",
            "Most likely still dry; nothing to worry about.",
        )

    if dbz > 0 and dbz < CONFIRM_DBZ:
        if lang == "vi":
            return pack(
                f"Chỉ có echo yếu (~{dbz:.0f} dBZ) cách {distance_text} hướng {dir_text} — "
                "thường là mây/mưa trên cao, chưa chắc xuống tới mặt đất.",
                "Nhiều khả năng chưa mưa; theo dõi thêm nếu trời tối đi.",
            )
        return pack(
            f"Only a weak echo (~{dbz:.0f} dBZ) {distance_text} toward {direction} — "
            "usually aloft, not necessarily reaching the ground.",
            "Probably not raining; keep an eye out if the sky darkens.",
        )

    if approaching and eta_minutes > 0:
        if lang == "vi":
            motion_bit = f" Đang dịch chuyển {motion_text}" if motion_text else ""
            speed_bit = f" (~{speed_kmh:.0f} km/h)" if speed_kmh >= 1 else ""
            explanation = (
                f"Mưa đang tiến tới từ hướng {dir_text}. "
                f"Cách khoảng {distance_text}, ETA ~{eta_minutes} phút."
                f"{motion_bit}{speed_bit}."
            )
            if eta_minutes <= 8:
                advice = "Chỉ ra ngoài nếu nhanh — mưa có thể trong ~10 phút."
            elif eta_minutes <= 20:
                advice = "Ra ngoài ngắn được; nhớ mang ô."
            else:
                advice = "Tạm thời ra ngoài được; theo dõi radar."
            return pack(explanation, advice)

        motion_bit = f" Moving {motion_direction}" if motion_direction else ""
        speed_bit = f" (~{speed_kmh:.0f} km/h)" if speed_kmh >= 1 else ""
        explanation = (
            f"Rain is approaching from {direction}. "
            f"About {distance_text} away, ETA ~{eta_minutes} min."
            f"{motion_bit}{speed_bit}."
        )
        if eta_minutes <= 8:
            advice = "Go only if quick — rain likely within ~10 minutes."
        elif eta_minutes <= 20:
            advice = "OK to step out briefly; bring an umbrella."
        else:
            advice = "Fine to go outside for now; keep an eye on the radar."
        return pack(explanation, advice)

    if moving_away:
        # Still unsafe to call it a good outdoor window when rain is within ~8 km
        if distance_m <= 8000:
            if lang == "vi":
                return pack(
                    f"Mưa đang xa dần nhưng vẫn còn gần (~{distance_text} hướng {dir_text}).",
                    "Đừng yên tâm quá — nên mang ô phòng thân.",
                )
            return pack(
                f"Rain is moving away but still close (~{distance_text} toward {direction}).",
                "Don't assume it's clear — bring an umbrella.",
            )
        if lang == "vi":
            return pack(
                f"Mưa đang xa dần. Ô mưa gần nhất khoảng {distance_text} hướng {dir_text}.",
                "Ô lớn đã xa, nhưng mưa nhỏ/phùn vẫn có thể còn — nên mang ô nếu ra đường.",
            )
        return pack(
            f"Rain is moving away. Nearest cell about {distance_text} toward {direction}.",
            "The main cell is farther, but light drizzle can linger — bring an umbrella outdoors.",
        )

    if distance_m <= 5_000:
        if lang == "vi":
            return pack(
                f"Ô mưa cách {distance_text} hướng {dir_text} — chỗ bạn có thể vẫn ráo.",
                "Mưa quanh đây nhưng chưa trùm lên bạn; mang ô nếu đi xa.",
            )
        return pack(
            f"A cell sits {distance_text} toward {direction} — your spot may still be dry.",
            "Rain is around but not over you; take an umbrella if you go far.",
        )

    if speed_kmh < 1:
        if lang == "vi":
            return pack(
                f"Mưa gần nhất khoảng {distance_text} hướng {dir_text}.",
                "Gần nhưng chưa rõ đang tới — nên mang ô.",
            )
        return pack(
            f"Nearest rain is about {distance_text} away toward {direction}.",
            "Nearby but not clearly moving toward you — still safer with an umbrella.",
        )

    if lang == "vi":
        return pack(
            f"Mưa gần nhất khoảng {distance_text} hướng {dir_text}.",
            "Có mưa gần. Đi ngắn được; mang ô phòng thân.",
        )
    return pack(
        f"Nearest rain is about {distance_text} away toward {direction}.",
        "Rain is nearby. Fine for a short trip; bring an umbrella just in case.",
    )


def _format_distance(distance_m: int, lang: Lang) -> str:
    if distance_m >= 1000:
        return f"{distance_m / 1000:.1f} km"
    return f"{distance_m} m"
