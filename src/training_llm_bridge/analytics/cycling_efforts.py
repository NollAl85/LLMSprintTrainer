"""Cycling effort extraction and transparent activity classification."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from training_llm_bridge.analytics import ANALYTICS_TIMEZONE, POWER_DURATIONS_SEC
from training_llm_bridge.analytics.config_loader import load_analytics_config


@dataclass(frozen=True)
class BaselinesConfig:
    """Baseline settings.

    `lookback_days` is a practical heuristic window, not a validated physiology model.
    """

    lookback_days: int = 90
    durations_sec: list[int] = field(default_factory=lambda: POWER_DURATIONS_SEC.copy())


@dataclass(frozen=True)
class CyclingClassificationConfig:
    """Cycling classification thresholds.

    These are practical heuristics for sprint/kilo review, not validated physiology.
    """

    near_max_threshold: float = 0.95
    pmax_sprint_min_efforts_1_20s: int = 1
    pmax_frc_min_efforts_30_60s: int = 1
    frc_anaerobic_min_efforts_30_180s: int = 2
    severe_vo2_min_efforts_180_300s: int = 1
    recovery_max_intensity: float = 0.60
    recovery_max_load: int = 35
    recovery_max_duration_sec: int = 5400
    z2_min_duration_sec: int = 1800
    z2_max_intensity: float = 0.75
    mixed_hard_min_load: int = 70
    mixed_hard_min_intensity: float = 0.85

    @classmethod
    def from_yaml(cls) -> "CyclingClassificationConfig":
        """Load thresholds from default YAML or env override."""

        values = load_analytics_config("cycling_classification.yaml")
        allowed = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in values.items() if key in allowed})


def extract_power_series(activity: dict) -> list[tuple[int, int]] | None:
    """Extract `(seconds, watts)` samples from activity streams."""

    return _extract_stream_series(activity, stream_names={"watts", "power"})


def extract_cadence_series(activity: dict) -> list[tuple[int, int]] | None:
    """Extract `(seconds, cadence)` samples from activity streams."""

    return _extract_stream_series(activity, stream_names={"cadence"})


def extract_ss_power_model(activity: dict) -> dict[str, float | None]:
    """Extract Intervals.icu SS power-model fields without unit conversion."""

    return {
        "ss_cp": _first_number(activity, ["ss_cp"]),
        "ss_p_max": _first_number(activity, ["ss_p_max"]),
        "ss_w_prime": _first_number(activity, ["ss_w_prime"]),
    }


def compute_best_power_windows(
    power_series: list[tuple[int, int]], durations_sec: list[int]
) -> dict[int, int]:
    """Compute best rolling average power for each duration."""

    if not power_series:
        return {}
    ordered = sorted((int(t), int(p)) for t, p in power_series if p is not None)
    watts = [point[1] for point in ordered]
    prefix = [0]
    for value in watts:
        prefix.append(prefix[-1] + value)

    best: dict[int, int] = {}
    for duration in durations_sec:
        if duration <= 0 or len(watts) < duration:
            continue
        max_avg = 0.0
        for idx in range(0, len(watts) - duration + 1):
            total = prefix[idx + duration] - prefix[idx]
            max_avg = max(max_avg, total / duration)
        best[int(duration)] = int(round(max_avg))
    return best


def build_power_baselines(activities: list[dict], lookback_days: int = 90) -> dict:
    """Build rolling max power baselines for the last `lookback_days` in the input."""

    deduped = _dedupe_activities(activities)
    dated = [(activity, _activity_date(activity)) for activity in deduped]
    dated = [(activity, activity_date) for activity, activity_date in dated if activity_date]
    if not dated:
        return {
            "heuristic": True,
            "basis": "no dated activities",
            "lookback_days": lookback_days,
            "durations_sec": POWER_DURATIONS_SEC.copy(),
            "max_power_watts": {},
            "activity_ids_by_duration": {},
            "missing_metrics": [f"baseline_{duration}s" for duration in POWER_DURATIONS_SEC],
        }

    latest = max(activity_date for _activity, activity_date in dated)
    cutoff = latest - timedelta(days=lookback_days)
    max_power: dict[int, int] = {}
    activity_ids: dict[int, str | None] = {}

    for activity, activity_date in dated:
        if activity_date < cutoff:
            continue
        windows = _activity_best_windows(activity, POWER_DURATIONS_SEC)
        for duration, watts in windows.items():
            if watts > max_power.get(duration, 0):
                max_power[duration] = watts
                activity_ids[duration] = str(activity.get("id")) if activity.get("id") else None

    missing = [f"baseline_{duration}s" for duration in POWER_DURATIONS_SEC if duration not in max_power]
    return {
        "heuristic": True,
        "basis": "rolling max from streams and available summary fields",
        "lookback_days": lookback_days,
        "durations_sec": POWER_DURATIONS_SEC.copy(),
        "max_power_watts": {str(key): value for key, value in sorted(max_power.items())},
        "activity_ids_by_duration": {str(key): value for key, value in sorted(activity_ids.items())},
        "missing_metrics": missing,
    }


def detect_near_max_efforts(
    power_series: list[tuple[int, int]],
    baselines: dict,
    durations_sec: list[int],
    threshold: float = 0.95,
) -> dict[int, int]:
    """Count rolling windows at or above a fraction of baseline for each duration."""

    baseline_map = baselines.get("max_power_watts", baselines)
    ordered = sorted((int(t), int(p)) for t, p in power_series if p is not None)
    watts = [point[1] for point in ordered]
    prefix = [0]
    for value in watts:
        prefix.append(prefix[-1] + value)

    counts: dict[int, int] = {}
    for duration in durations_sec:
        baseline = _baseline_value(baseline_map, duration)
        if baseline is None or baseline <= 0 or len(watts) < duration:
            counts[int(duration)] = 0
            continue
        count = 0
        for idx in range(0, len(watts) - duration + 1):
            total = prefix[idx + duration] - prefix[idx]
            if total / duration >= baseline * threshold:
                count += 1
        counts[int(duration)] = count
    return counts


def classify_cycling_activity(
    activity: dict,
    baselines: dict | None = None,
    config: CyclingClassificationConfig = CyclingClassificationConfig(),
) -> dict:
    """Classify one cycling activity with transparent heuristic evidence."""

    if config == CyclingClassificationConfig():
        config = CyclingClassificationConfig.from_yaml()

    power_series = extract_power_series(activity)
    cadence_series = extract_cadence_series(activity)
    ss_power_model = extract_ss_power_model(activity)
    best_power = _activity_best_windows(activity, POWER_DURATIONS_SEC)
    missing_metrics: list[str] = []
    near_max = {duration: 0 for duration in POWER_DURATIONS_SEC}
    basis = "unknown"
    primary_tag = "unknown"
    tags: list[str] = []

    if power_series and baselines:
        near_max = detect_near_max_efforts(
            power_series,
            baselines,
            POWER_DURATIONS_SEC,
            threshold=config.near_max_threshold,
        )
        primary_tag, tags = _classify_from_near_max(near_max, config)
        if primary_tag != "unknown":
            basis = "from streams + baselines"

    if primary_tag == "unknown":
        primary_tag, tags = _classify_from_summary_fields(activity, best_power)
        if primary_tag != "unknown":
            basis = "from activity summary best-effort fields"

    if primary_tag == "unknown":
        primary_tag, tags = _classify_from_text(activity)
        if primary_tag != "unknown":
            basis = "from summary tags/name/interval names"

    if primary_tag == "unknown":
        primary_tag, tags = _classify_from_load_intensity_duration(activity, config)
        basis = "fallback from load + intensity + duration"

    for duration in POWER_DURATIONS_SEC:
        if duration not in best_power:
            missing_metrics.append(f"best_power_{duration}s")
    if not power_series:
        missing_metrics.append("power_stream")
    if not cadence_series:
        missing_metrics.append("cadence_stream")
    for key, value in ss_power_model.items():
        if value is None:
            missing_metrics.append(key)

    return {
        "activity_id": activity.get("id"),
        "basis": basis,
        "best_power_watts": {str(key): value for key, value in sorted(best_power.items())},
        "cadence_stream_available": cadence_series is not None,
        "date": _activity_date_string(activity),
        "duration_seconds": _int_or_none(
            _first_number(activity, ["moving_time", "elapsed_time", "icu_recording_time", "duration"])
        ),
        "evidence": {
            "activity_type": activity.get("type"),
            "intensity": _normalized_intensity(activity),
            "interval_summary": activity.get("interval_summary"),
            "name": activity.get("name"),
            "start_time": activity.get("start_date_local") or activity.get("start_date"),
            "training_load": _first_number(activity, ["icu_training_load", "training_load", "power_load"]),
        },
        "heuristic": True,
        "missing_metrics": sorted(set(missing_metrics)),
        "name": activity.get("name"),
        "near_max_efforts": {str(key): value for key, value in sorted(near_max.items())},
        "primary_tag": primary_tag,
        "source": "intervals_icu",
        "ss_power_model": ss_power_model,
        "tags": tags,
    }


def _extract_stream_series(activity: dict, *, stream_names: set[str]) -> list[tuple[int, int]] | None:
    streams = activity.get("streams") or activity.get("activity_streams")
    if streams is None:
        return None

    time_values: list[int] | None = None
    target_values: list[int] | None = None

    if isinstance(streams, dict):
        time_raw = streams.get("time") or streams.get("seconds")
        time_values = _int_list(time_raw) if isinstance(time_raw, list) else None
        for name in stream_names:
            values = streams.get(name)
            if isinstance(values, list):
                target_values = _int_list(values)
                break

    if isinstance(streams, list):
        for stream in streams:
            if not isinstance(stream, dict):
                continue
            stream_type = str(stream.get("type") or stream.get("name") or "").lower()
            data = stream.get("data")
            if stream_type == "time" and isinstance(data, list):
                time_values = _int_list(data)
            if stream_type in stream_names and isinstance(data, list):
                target_values = _int_list(data)

    if not target_values:
        return None
    if not time_values or len(time_values) != len(target_values):
        time_values = list(range(len(target_values)))

    return [
        (int(second), int(value))
        for second, value in zip(time_values, target_values)
        if value is not None
    ]


def _activity_best_windows(activity: dict, durations: list[int]) -> dict[int, int]:
    power_series = extract_power_series(activity)
    windows = compute_best_power_windows(power_series, durations) if power_series else {}

    summary_map = _summary_power_fields(activity)
    for duration in durations:
        value = summary_map.get(duration)
        if value is not None:
            windows[duration] = max(windows.get(duration, 0), value)
    return windows


def _summary_power_fields(activity: dict) -> dict[int, int]:
    candidates = {
        300: ["Best5Minutepower", "best_5min_power", "best_300s_power"],
        1200: ["Best20minutespower", "best_20min_power", "best_1200s_power"],
    }
    output: dict[int, int] = {}
    for duration, keys in candidates.items():
        for key in keys:
            value = _first_number(activity, [key])
            if value is not None:
                output[duration] = int(round(value))
                break
    for key, value in activity.items():
        match = re.fullmatch(r"(?:power_|best_|max_)?(\d+)s(?:_power)?", str(key), re.I)
        if match:
            num = _to_number(value)
            if num is not None:
                output[int(match.group(1))] = int(round(num))
    return output


def _classify_from_near_max(
    near_max: dict[int, int], config: CyclingClassificationConfig
) -> tuple[str, list[str]]:
    tags = []
    if sum(near_max.get(duration, 0) for duration in (1, 5, 10, 15, 20)) >= config.pmax_sprint_min_efforts_1_20s:
        tags.append("pmax_sprint")
    if sum(near_max.get(duration, 0) for duration in (30, 45, 60)) >= config.pmax_frc_min_efforts_30_60s:
        tags.append("pmax_frc")
    if sum(near_max.get(duration, 0) for duration in (30, 45, 60, 120, 180)) >= config.frc_anaerobic_min_efforts_30_180s:
        tags.append("frc_anaerobic")
    if sum(near_max.get(duration, 0) for duration in (180, 300)) >= config.severe_vo2_min_efforts_180_300s:
        tags.append("severe_vo2")
    return (tags[0], tags) if tags else ("unknown", [])


def _classify_from_summary_fields(activity: dict, best_power: dict[int, int]) -> tuple[str, list[str]]:
    if any(duration in best_power for duration in (1, 5, 10, 15, 20)):
        return "pmax_sprint", ["pmax_sprint"]
    if any(duration in best_power for duration in (30, 45, 60)):
        return "pmax_frc", ["pmax_frc"]
    if best_power.get(300) or best_power.get(1200):
        return "severe_vo2", ["severe_vo2"]
    return "unknown", []


def _classify_from_text(activity: dict) -> tuple[str, list[str]]:
    parts: list[str] = []
    for key in ("name", "description", "tags", "interval_summary"):
        value = activity.get(key)
        if isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value:
            parts.append(str(value))
    text = " ".join(parts).lower()
    if any(token in text for token in ("sprint", "pmax", "max power")) or re.search(r"\b\d+x\s*\d{1,2}s\b", text):
        return "pmax_sprint", ["pmax_sprint"]
    if any(token in text for token in ("anaerobic", "frc", "30s", "45s", "60s")):
        return "frc_anaerobic", ["frc_anaerobic"]
    if any(token in text for token in ("vo2", "5 min", "5min")):
        return "severe_vo2", ["severe_vo2"]
    if any(token in text for token in ("recovery", "easy")):
        return "recovery_easy", ["recovery_easy"]
    if any(token in text for token in ("endurance", "z2", "zone 2")):
        return "z2_aerobic", ["z2_aerobic"]
    return "unknown", []


def _classify_from_load_intensity_duration(
    activity: dict, config: CyclingClassificationConfig
) -> tuple[str, list[str]]:
    duration = _first_number(activity, ["moving_time", "elapsed_time", "icu_recording_time", "duration"]) or 0
    load = _first_number(activity, ["icu_training_load", "training_load", "power_load"]) or 0
    intensity = _normalized_intensity(activity)

    if (
        duration <= config.recovery_max_duration_sec
        and load <= config.recovery_max_load
        and (intensity is None or intensity <= config.recovery_max_intensity)
    ):
        return "recovery_easy", ["recovery_easy"]
    if duration >= config.z2_min_duration_sec and intensity is not None and intensity <= config.z2_max_intensity:
        return "z2_aerobic", ["z2_aerobic"]
    if load >= config.mixed_hard_min_load or (
        intensity is not None and intensity >= config.mixed_hard_min_intensity
    ):
        return "mixed_hard", ["mixed_hard"]
    return "unknown", ["unknown"]


def _dedupe_activities(activities: list[dict]) -> list[dict]:
    seen = set()
    output = []
    for activity in activities:
        activity_id = activity.get("id")
        if activity_id and activity_id in seen:
            continue
        if activity_id:
            seen.add(activity_id)
        output.append(activity)
    return output


def _activity_date(activity: dict) -> date | None:
    value = activity.get("start_date_local") or activity.get("start_date") or activity.get("date")
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(ANALYTICS_TIMEZONE))
    return parsed.astimezone(ZoneInfo(ANALYTICS_TIMEZONE)).date()


def _activity_date_string(activity: dict) -> str | None:
    activity_date = _activity_date(activity)
    return activity_date.isoformat() if activity_date else None


def _baseline_value(baseline_map: dict, duration: int) -> float | None:
    return _to_number(baseline_map.get(duration) if duration in baseline_map else baseline_map.get(str(duration)))


def _normalized_intensity(activity: dict) -> float | None:
    value = _first_number(activity, ["icu_intensity", "intensity", "intensity_factor"])
    if value is None:
        return None
    return value / 100 if value > 2 else value


def _first_number(data: dict, keys: list[str]) -> float | None:
    for key in keys:
        value = _to_number(data.get(key))
        if value is not None:
            return value
    return None


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: float | None) -> int | None:
    return int(round(value)) if value is not None else None


def _int_list(values: list[Any]) -> list[int]:
    output = []
    for value in values:
        number = _to_number(value)
        output.append(int(round(number)) if number is not None else 0)
    return output
