"""Hevy strength-session classification with transparent movement heuristics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from training_llm_bridge.analytics import ANALYTICS_TIMEZONE
from training_llm_bridge.analytics.config_loader import load_analytics_config

MOVEMENT_PATTERNS = [
    "squat_pattern",
    "hinge_pattern",
    "unilateral_leg",
    "hamstring_eccentric",
    "calf_ankle",
    "upper_push",
    "upper_pull",
    "trunk_core",
    "other",
    "unknown",
]

LOWER_PATTERNS = {"squat_pattern", "hinge_pattern", "unilateral_leg", "hamstring_eccentric", "calf_ankle"}
UPPER_PATTERNS = {"upper_push", "upper_pull"}


@dataclass(frozen=True)
class StrengthClassificationConfig:
    """Strength classification thresholds.

    These are practical heuristics, not validated physiology.
    """

    max_strength_max_reps: int = 5
    max_strength_min_heavy_sets: int = 2
    hypertrophy_min_reps: int = 6
    hypertrophy_max_reps: int = 15
    hypertrophy_min_sets: int = 6
    power_explosive_max_reps: int = 3
    accessory_max_weight_kg: float = 30.0
    lower_body_set_share: float = 0.50
    upper_body_set_share: float = 0.50

    @classmethod
    def from_yaml(cls) -> "StrengthClassificationConfig":
        """Load thresholds from default YAML or env override."""

        values = load_analytics_config("strength_classification.yaml")
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in values.items() if key in allowed})


def classify_strength_workout(
    workout: dict,
    config: StrengthClassificationConfig = StrengthClassificationConfig(),
) -> dict:
    """Classify a Hevy workout by session type and movement pattern."""

    if config == StrengthClassificationConfig():
        config = StrengthClassificationConfig.from_yaml()

    movement_map = _load_movement_patterns()
    normalized = workout.get("workout", workout)
    exercises = normalized.get("exercises") or []
    movement_patterns = _empty_movement_patterns()
    uncertainty: list[str] = []
    total_sets = 0
    total_volume = 0.0
    heavy_sets = 0
    hypertrophy_sets = 0
    explosive_sets = 0
    weighted_sets = 0
    known_rpe = 0
    exercise_summaries = []

    for exercise in exercises:
        title = str(exercise.get("title") or exercise.get("name") or "unknown").strip() or "unknown"
        pattern = _match_movement_pattern(title, movement_map)
        if pattern == "unknown":
            uncertainty.append(f"Unknown movement pattern for exercise: {title}")

        sets = exercise.get("sets") or []
        exercise_sets = 0
        exercise_volume = 0.0
        for set_item in sets:
            reps = _num(set_item.get("reps"))
            weight = _num(set_item.get("weight_kg"))
            rpe = _num(set_item.get("rpe"))
            if rpe is not None:
                known_rpe += 1
            if reps is None:
                uncertainty.append(f"Missing reps for {title}")
                continue
            total_sets += 1
            exercise_sets += 1
            if weight is not None:
                weighted_sets += 1
                exercise_volume += max(weight, 0) * reps
            if reps <= config.max_strength_max_reps:
                heavy_sets += 1
            if config.hypertrophy_min_reps <= reps <= config.hypertrophy_max_reps:
                hypertrophy_sets += 1
            if reps <= config.power_explosive_max_reps and _looks_explosive(exercise, set_item):
                explosive_sets += 1

        total_volume += exercise_volume
        movement_patterns[pattern]["sets"] += exercise_sets
        movement_patterns[pattern]["volume_kg"] += round(exercise_volume, 2)
        if title not in movement_patterns[pattern]["exercises"]:
            movement_patterns[pattern]["exercises"].append(title)
        exercise_summaries.append(
            {
                "exercise_template_id": exercise.get("exercise_template_id"),
                "movement_pattern": pattern,
                "sets": exercise_sets,
                "title": title,
                "volume_kg": round(exercise_volume, 2),
            }
        )

    if known_rpe == 0:
        uncertainty.append("RPE/RIR/e1RM mostly unavailable; session tags use rep-range heuristics.")

    session_tags = _session_tags(
        movement_patterns,
        total_sets,
        heavy_sets,
        hypertrophy_sets,
        explosive_sets,
        weighted_sets,
        total_volume,
        config,
    )
    primary_tag = session_tags[0] if session_tags else "unknown"

    return {
        "basis": "from Hevy exercise titles + sets/reps/load",
        "date": _workout_date_string(normalized),
        "duration_seconds": _duration_seconds(normalized),
        "evidence": {
            "heavy_sets": heavy_sets,
            "hypertrophy_sets": hypertrophy_sets,
            "known_rpe_sets": known_rpe,
            "weighted_sets": weighted_sets,
        },
        "exercise_summaries": exercise_summaries,
        "heuristic": True,
        "missing_metrics": _missing_metrics(normalized, known_rpe),
        "movement_patterns": _clean_movement_patterns(movement_patterns),
        "primary_session_tag": primary_tag,
        "session_tags": session_tags or ["unknown"],
        "source": "hevy",
        "title": normalized.get("title"),
        "total_sets": total_sets,
        "total_volume_kg": round(total_volume, 2),
        "uncertainty": sorted(set(uncertainty)),
        "workout_id": normalized.get("id"),
    }


def _load_movement_patterns() -> dict[str, list[str]]:
    data = load_analytics_config("movement_patterns.yaml")
    return {
        pattern: [str(item).lower() for item in values]
        for pattern, values in data.items()
        if isinstance(values, list)
    }


def _empty_movement_patterns() -> dict[str, dict[str, Any]]:
    return {pattern: {"sets": 0, "volume_kg": 0.0, "exercises": []} for pattern in MOVEMENT_PATTERNS}


def _match_movement_pattern(title: str, movement_map: dict[str, list[str]]) -> str:
    lower = title.lower()
    matches: list[tuple[int, str]] = []
    for pattern, needles in movement_map.items():
        for needle in needles:
            if needle in lower:
                matches.append((len(needle), pattern))
    if not matches:
        return "unknown"
    return sorted(matches, reverse=True)[0][1]


def _session_tags(
    movement_patterns: dict[str, dict[str, Any]],
    total_sets: int,
    heavy_sets: int,
    hypertrophy_sets: int,
    explosive_sets: int,
    weighted_sets: int,
    total_volume: float,
    config: StrengthClassificationConfig,
) -> list[str]:
    if total_sets == 0:
        return ["unknown"]

    tags = []
    if heavy_sets >= config.max_strength_min_heavy_sets:
        tags.append("max_strength")
    if hypertrophy_sets >= config.hypertrophy_min_sets:
        tags.append("hypertrophy")
    if explosive_sets > 0:
        tags.append("power_explosive")
    if weighted_sets and total_volume / max(weighted_sets, 1) <= config.accessory_max_weight_kg:
        tags.append("accessory_prehab")

    lower_sets = sum(movement_patterns[pattern]["sets"] for pattern in LOWER_PATTERNS)
    upper_sets = sum(movement_patterns[pattern]["sets"] for pattern in UPPER_PATTERNS)
    lower_share = lower_sets / total_sets
    upper_share = upper_sets / total_sets
    if lower_share >= config.lower_body_set_share and upper_share >= 0.25:
        tags.append("mixed")
    elif lower_share >= config.lower_body_set_share:
        tags.append("lower_body")
    elif upper_share >= config.upper_body_set_share:
        tags.append("upper_body")
    elif lower_sets and upper_sets:
        tags.append("mixed")

    return _dedupe(tags) or ["unknown"]


def _looks_explosive(exercise: dict, set_item: dict) -> bool:
    text = " ".join(
        str(value or "")
        for value in (exercise.get("title"), exercise.get("notes"), set_item.get("type"))
    ).lower()
    return any(token in text for token in ("jump", "power", "plyo", "explosive", "speed"))


def _missing_metrics(workout: dict, known_rpe: int) -> list[str]:
    missing = ["rir", "e1rm"]
    if known_rpe == 0:
        missing.append("rpe")
    if not workout.get("start_time"):
        missing.append("start_time")
    return sorted(missing)


def _clean_movement_patterns(patterns: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    cleaned = {}
    for pattern, values in patterns.items():
        cleaned[pattern] = {
            "exercises": sorted(values["exercises"]),
            "sets": int(values["sets"]),
            "volume_kg": round(float(values["volume_kg"]), 2),
        }
    return cleaned


def _workout_date_string(workout: dict) -> str | None:
    value = workout.get("start_time") or workout.get("date")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10]).isoformat()
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(ANALYTICS_TIMEZONE))
    return parsed.astimezone(ZoneInfo(ANALYTICS_TIMEZONE)).date().isoformat()


def _duration_seconds(workout: dict) -> int | None:
    start = _parse_datetime(workout.get("start_time"))
    end = _parse_datetime(workout.get("end_time"))
    if not start or not end:
        return None
    return int((end - start).total_seconds())


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(ANALYTICS_TIMEZONE))
    return parsed.astimezone(ZoneInfo(ANALYTICS_TIMEZONE))


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dedupe(values: list[str]) -> list[str]:
    output = []
    for value in values:
        if value not in output:
            output.append(value)
    return output
