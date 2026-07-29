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
) -> tuple[RainChance, int]:
    """Heuristic nowcast chance at the user's spot (not a NWP forecast)."""
    if not has_rain:
        return "none", 8

    score = 18.0
    if distance_m <= 250:
        score += 55
    elif distance_m <= 1500:
        score += 40
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
) -> tuple[bool, bool]:
    if not has_rain:
        return False, False
    if distance_m <= 1500:
        return True, True
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
) -> AdviceResult:
    """Deterministic nowcast copy — no LLM."""
    chance, pct = estimate_rain_chance(
        has_rain=has_rain,
        distance_m=distance_m,
        approaching=approaching,
        eta_minutes=eta_minutes,
        intensity=intensity,
    )
    rain_in_1h, rain_in_2h = _horizon_rain_flags(
        has_rain=has_rain,
        distance_m=distance_m,
        approaching=approaching,
        eta_minutes=eta_minutes,
        pct=pct,
    )
    chance_bit = _chance_line(chance, pct, lang)

    if not has_rain:
        if lang == "vi":
            return AdviceResult(
                explanation="Không phát hiện mưa gần đây.",
                advice=f"{chance_bit} Thời điểm tốt để ra ngoài.",
                rain_chance=chance,
                rain_chance_pct=pct,
                rain_in_1h=rain_in_1h,
                rain_in_2h=rain_in_2h,
            )
        return AdviceResult(
            explanation="No rain detected nearby.",
            advice=f"{chance_bit} Good window to go outside.",
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

    if distance_m <= 250:
        if lang == "vi":
            return pack(
                f"Mưa rất gần — khoảng {distance_text} hướng {dir_text}.",
                "Nên trú mưa hoặc mang ô ngay.",
            )
        return pack(
            f"Rain is very close — about {distance_text} toward {direction}.",
            "Stay covered or bring an umbrella now.",
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
        if lang == "vi":
            return pack(
                f"Mưa đang xa dần. Ô mưa gần nhất khoảng {distance_text} hướng {dir_text}.",
                "Thời điểm tốt để ra ngoài.",
            )
        return pack(
            f"Rain is moving away. Nearest cell about {distance_text} toward {direction}.",
            "Good window to go outside.",
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
