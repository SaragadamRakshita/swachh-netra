"""
Core business logic:
- Evaluate sensor readings against thresholds
- Calculate facility score
- Determine alert severity
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple


# ── Thresholds ──
THRESHOLDS = {
    "nh3": {
        "clean":   (0, 25),
        "warning": (25, 50),
        "critical": (50, 999),
    },
    "voc": {
        "clean":   (0, 40),
        "warning": (40, 65),
        "critical": (65, 999),
    },
    "door_count": {
        "clean":   (0, 60),
        "warning": (60, 120),
        "critical": (120, 9999),
    },
    "humidity": {
        "clean":   (0, 75),
        "warning": (75, 85),
        "critical": (85, 100),
    },
    "temperature": {
        "clean":   (0, 35),
        "warning": (35, 40),
        "critical": (40, 99),
    },
}

NH3_CLEAN_THRESHOLD    = 25
NH3_WARNING_THRESHOLD  = 50
VOC_CLEAN_THRESHOLD    = 40
VOC_WARNING_THRESHOLD  = 65
DOOR_CLEAN_THRESHOLD   = 60
DOOR_WARNING_THRESHOLD = 120


@dataclass
class AlertTrigger:
    sensor: str
    value: float
    threshold: float
    severity: str
    message: str


def get_severity(sensor: str, value: float) -> str:
    """Return 'ok' | 'warning' | 'critical' for a sensor value."""
    t = THRESHOLDS.get(sensor, {})
    w_lo, w_hi = t.get("warning", (999, 999))
    c_lo, _    = t.get("critical", (9999, 9999))
    if value >= c_lo:
        return "critical"
    if value >= w_lo:
        return "warning"
    return "ok"


def evaluate_reading(
    nh3: float,
    voc: float,
    doors: int,
    humidity: float,
    temperature: Optional[float] = None,
    water_flow: Optional[float] = None,
) -> Tuple[str, List[AlertTrigger]]:
    """
    Returns (facility_status, list_of_alert_triggers).
    facility_status is the worst severity found.
    """
    triggers: List[AlertTrigger] = []

    checks = [
        ("nh3",       nh3,       NH3_WARNING_THRESHOLD,   f"NH₃ level: {nh3:.0f} ppm"),
        ("nh3",       nh3,       NH3_CLEAN_THRESHOLD,     f"NH₃ warning: {nh3:.0f} ppm"),
        ("voc",       voc,       VOC_WARNING_THRESHOLD,   f"VOC level: {voc:.0f} ppm"),
        ("voc",       voc,       VOC_CLEAN_THRESHOLD,     f"VOC warning: {voc:.0f} ppm"),
        ("door_count",doors,     DOOR_WARNING_THRESHOLD,  f"Usage exceeded: {doors} uses"),
        ("door_count",doors,     DOOR_CLEAN_THRESHOLD,    f"Usage warning: {doors} uses"),
    ]

    if nh3 > NH3_WARNING_THRESHOLD:
        triggers.append(AlertTrigger("nh3", nh3, NH3_WARNING_THRESHOLD, "critical",
                                     f"NH₃ critical: {nh3:.0f} ppm (threshold: {NH3_WARNING_THRESHOLD} ppm)"))
    elif nh3 > NH3_CLEAN_THRESHOLD:
        triggers.append(AlertTrigger("nh3", nh3, NH3_CLEAN_THRESHOLD, "warning",
                                     f"NH₃ elevated: {nh3:.0f} ppm"))

    if voc > VOC_WARNING_THRESHOLD:
        triggers.append(AlertTrigger("voc", voc, VOC_WARNING_THRESHOLD, "critical",
                                     f"VOC critical: {voc:.0f} ppm"))
    elif voc > VOC_CLEAN_THRESHOLD:
        triggers.append(AlertTrigger("voc", voc, VOC_CLEAN_THRESHOLD, "warning",
                                     f"VOC elevated: {voc:.0f} ppm"))

    if doors > DOOR_WARNING_THRESHOLD:
        triggers.append(AlertTrigger("door_count", doors, DOOR_WARNING_THRESHOLD, "critical",
                                     f"Usage critical: {doors} uses today"))
    elif doors > DOOR_CLEAN_THRESHOLD:
        triggers.append(AlertTrigger("door_count", doors, DOOR_CLEAN_THRESHOLD, "warning",
                                     f"Usage elevated: {doors} uses today"))

    if water_flow is not None and water_flow == 0:
        triggers.append(AlertTrigger("water_flow", 0, 0.1, "critical", "Water flow failure: sensor reads 0"))

    if humidity > 85:
        triggers.append(AlertTrigger("humidity", humidity, 85, "warning",
                                     f"High humidity: {humidity:.0f}% — increases odour risk"))

    if not triggers:
        return "ok", []
    worst = max(t.severity for t in triggers)
    status = "alert" if worst == "critical" else "warning"
    return status, triggers


def calculate_score(
    nh3: float,
    voc: float,
    doors: int,
    last_cleaned_minutes_ago: int,
    water_flow: Optional[float] = None,
) -> int:
    """
    Score formula (0–100):
      40% Odor Index   (NH₃ + VOC combined)
      30% Clean Frequency
      20% Footfall compliance
      10% Infrastructure
    """
    # Odor score (lower ppm = higher score)
    nh3_score = max(0, 100 - (nh3 / NH3_WARNING_THRESHOLD) * 50)
    voc_score  = max(0, 100 - (voc / VOC_WARNING_THRESHOLD) * 50)
    odor_score = (nh3_score + voc_score) / 2

    # Cleaning frequency score
    if last_cleaned_minutes_ago <= 30:
        clean_score = 100
    elif last_cleaned_minutes_ago <= 60:
        clean_score = 85
    elif last_cleaned_minutes_ago <= 120:
        clean_score = 65
    elif last_cleaned_minutes_ago <= 240:
        clean_score = 40
    else:
        clean_score = 15

    # Footfall compliance
    if doors <= DOOR_CLEAN_THRESHOLD:
        foot_score = 100
    elif doors <= DOOR_WARNING_THRESHOLD:
        foot_score = 60
    else:
        foot_score = 25

    # Infrastructure (water)
    infra_score = 100 if (water_flow is None or water_flow > 0) else 20

    score = (
        odor_score  * 0.40 +
        clean_score * 0.30 +
        foot_score  * 0.20 +
        infra_score * 0.10
    )
    return max(0, min(100, round(score)))


def city_score_from_facilities(scores: list[int]) -> int:
    """Weighted average city score from list of facility scores."""
    if not scores:
        return 0
    return round(sum(scores) / len(scores))
