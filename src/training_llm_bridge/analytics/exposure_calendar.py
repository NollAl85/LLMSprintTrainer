"""Daily exposure calendar assembly."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from training_llm_bridge.analytics import ANALYTICS_TIMEZONE


def build_daily_exposure_calendar(
    classified_cycling: list[dict],
    classified_strength: list[dict],
    baselines: dict,
    wellness: list[dict] | None = None,
) -> list[dict]:
    """Merge classified cycling, strength, and wellness into daily rows."""

    wellness = wellness or []
    dates = sorted(
        {
            item["date"]
            for item in classified_cycling + classified_strength
            if item.get("date")
        }
        | {_wellness_date(item) for item in wellness if _wellness_date(item)}
    )

    cycling_by_date: dict[str, list[dict]] = defaultdict(list)
    strength_by_date: dict[str, list[dict]] = defaultdict(list)
    wellness_by_date: dict[str, dict] = {}

    for item in classified_cycling:
        if item.get("date"):
            cycling_by_date[item["date"]].append(item)
    for item in classified_strength:
        if item.get("date"):
            strength_by_date[item["date"]].append(item)
    for item in wellness:
        item_date = _wellness_date(item)
        if item_date:
            wellness_by_date[item_date] = item

    rows = []
    for row_date in dates:
        cycling_summary = _summarize_cycling(cycling_by_date.get(row_date, []))
        strength_summary = _summarize_strength(strength_by_date.get(row_date, []))
        wellness_summary = _summarize_wellness(wellness_by_date.get(row_date))
        rows.append(
            {
                "baselines": {
                    "basis": baselines.get("basis"),
                    "lookback_days": baselines.get("lookback_days"),
                    "max_power_watts": baselines.get("max_power_watts", {}),
                    "missing_metrics": baselines.get("missing_metrics", []),
                },
                "cycling": cycling_summary,
                "date": row_date,
                "missing_metrics": sorted(
                    set(
                        cycling_summary.get("missing_metrics", [])
                        + strength_summary.get("missing_metrics", [])
                        + wellness_summary.get("missing_metrics", [])
                    )
                ),
                "strength": strength_summary,
                "wellness": wellness_summary,
            }
        )
    return rows


def _summarize_cycling(items: list[dict]) -> dict:
    if not items:
        return {
            "activity_count": 0,
            "activity_ids": [],
            "best_power_watts": {},
            "duration_seconds": 0,
            "missing_metrics": [],
            "near_max_efforts": {},
            "primary_tags": [],
            "ss_power_model": {"latest": None, "records": []},
            "tags": [],
            "training_load": 0,
        }
    best_power: dict[str, int] = {}
    near_max: dict[str, int] = defaultdict(int)
    missing = []
    tags = []
    primary_tags = []
    duration = 0
    training_load = 0.0
    ss_records = []
    for item in items:
        duration += int(item.get("duration_seconds") or 0)
        training_load += _number(item.get("evidence", {}).get("training_load")) or 0
        tags.extend(item.get("tags", []))
        if item.get("primary_tag"):
            primary_tags.append(item["primary_tag"])
        missing.extend(item.get("missing_metrics", []))
        for key, value in item.get("best_power_watts", {}).items():
            if value is not None:
                best_power[key] = max(int(value), best_power.get(key, 0))
        for key, value in item.get("near_max_efforts", {}).items():
            near_max[key] += int(value or 0)
        ss_power_model = item.get("ss_power_model") or {}
        if any(ss_power_model.get(key) is not None for key in ("ss_cp", "ss_p_max", "ss_w_prime")):
            ss_records.append(
                {
                    "activity_id": item.get("activity_id"),
                    "ss_cp": ss_power_model.get("ss_cp"),
                    "ss_p_max": ss_power_model.get("ss_p_max"),
                    "ss_w_prime": ss_power_model.get("ss_w_prime"),
                }
            )
    return {
        "activity_count": len(items),
        "activity_ids": [item.get("activity_id") for item in items],
        "best_power_watts": dict(sorted(best_power.items(), key=lambda pair: int(pair[0]))),
        "duration_seconds": duration,
        "missing_metrics": sorted(set(missing)),
        "near_max_efforts": dict(sorted(near_max.items(), key=lambda pair: int(pair[0]))),
        "primary_tags": _dedupe(primary_tags),
        "ss_power_model": {"latest": ss_records[-1] if ss_records else None, "records": ss_records},
        "tags": _dedupe(tags),
        "training_load": round(training_load, 2),
    }


def _summarize_strength(items: list[dict]) -> dict:
    if not items:
        return {
            "missing_metrics": [],
            "movement_patterns": {},
            "primary_session_tags": [],
            "session_tags": [],
            "total_sets": 0,
            "total_volume_kg": 0,
            "uncertainty": [],
            "workout_count": 0,
            "workout_ids": [],
        }
    movement_patterns: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"sets": 0, "volume_kg": 0.0, "exercises": []}
    )
    missing = []
    uncertainty = []
    session_tags = []
    primary_tags = []
    total_sets = 0
    total_volume = 0.0
    for item in items:
        total_sets += int(item.get("total_sets") or 0)
        total_volume += _number(item.get("total_volume_kg")) or 0
        missing.extend(item.get("missing_metrics", []))
        uncertainty.extend(item.get("uncertainty", []))
        session_tags.extend(item.get("session_tags", []))
        if item.get("primary_session_tag"):
            primary_tags.append(item["primary_session_tag"])
        for pattern, values in (item.get("movement_patterns") or {}).items():
            movement_patterns[pattern]["sets"] += int(values.get("sets") or 0)
            movement_patterns[pattern]["volume_kg"] += _number(values.get("volume_kg")) or 0
            movement_patterns[pattern]["exercises"].extend(values.get("exercises", []))

    return {
        "missing_metrics": sorted(set(missing)),
        "movement_patterns": {
            pattern: {
                "exercises": sorted(set(values["exercises"])),
                "sets": values["sets"],
                "volume_kg": round(values["volume_kg"], 2),
            }
            for pattern, values in sorted(movement_patterns.items())
            if values["sets"] or values["exercises"]
        },
        "primary_session_tags": _dedupe(primary_tags),
        "session_tags": _dedupe(session_tags),
        "total_sets": total_sets,
        "total_volume_kg": round(total_volume, 2),
        "uncertainty": sorted(set(uncertainty)),
        "workout_count": len(items),
        "workout_ids": [item.get("workout_id") for item in items],
    }


def _summarize_wellness(item: dict | None) -> dict:
    if not item:
        return {
            "atl": None,
            "ctl": None,
            "fatigue": None,
            "hrv": None,
            "missing_metrics": ["wellness"],
            "mood": None,
            "resting_hr": None,
            "sleep_secs": None,
            "soreness": None,
        }
    fields = {
        "atl": item.get("atl"),
        "ctl": item.get("ctl"),
        "fatigue": item.get("fatigue"),
        "hrv": item.get("hrv"),
        "mood": item.get("mood"),
        "resting_hr": item.get("restingHR"),
        "sleep_secs": item.get("sleepSecs"),
        "soreness": item.get("soreness"),
    }
    missing = [key for key, value in fields.items() if value is None]
    return {**fields, "missing_metrics": missing}


def _wellness_date(item: dict) -> str | None:
    value = item.get("id") or item.get("date")
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=ZoneInfo(ANALYTICS_TIMEZONE))
        return parsed.astimezone(ZoneInfo(ANALYTICS_TIMEZONE)).date().isoformat()


def _number(value: Any) -> float | None:
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
