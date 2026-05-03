"""Build compact cycling context from Intervals.icu records."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from training_llm_bridge.contexts.models import CyclingContext

CYCLING_TYPES = {
    "Ride",
    "VirtualRide",
    "GravelRide",
    "MountainBikeRide",
    "EBikeRide",
    "EMountainBikeRide",
}

SPRINT_DURATIONS = (5, 10, 15, 30, 60)


def build_cycling_context(
    activities: list[dict],
    wellness: list[dict] | None = None,
    events: list[dict] | None = None,
) -> dict:
    """Build a compact JSON-serializable cycling context."""

    wellness = wellness or []
    events = events or []
    rides = [_normalize_activity(activity) for activity in activities if _is_cycling(activity)]
    rides.sort(key=lambda item: item["start_dt"] or datetime.min.replace(tzinfo=timezone.utc))

    dated = [activity for activity in rides if activity["start_dt"]]
    start_dt = dated[0]["start_dt"] if dated else None
    end_dt = dated[-1]["start_dt"] if dated else None

    total_duration = sum(_num(activity.get("duration_seconds")) or 0 for activity in rides)
    total_distance = sum(_num(activity.get("distance_m")) or 0 for activity in rides)
    total_work_kj = _sum_available(activity.get("work_kj") for activity in rides)
    total_load = _sum_available(activity.get("training_load") for activity in rides)
    weekly = _weekly_rollups(rides)
    sprint_metrics, missing_metrics = _sprint_power_metrics(rides)
    wellness_summary = _wellness_summary(wellness)
    sprint_events = _sprint_events(events)
    flags = _cycling_flags(rides, weekly, sprint_metrics, wellness_summary, sprint_events)

    context = CyclingContext(
        integrated=True,
        source="intervals_icu",
        date_range={"start": _date_string(start_dt), "end": _date_string(end_dt)},
        number_of_cycling_activities=len(rides),
        total_duration_seconds=int(total_duration),
        total_duration_hours=_round(total_duration / 3600),
        total_distance_m=_round(total_distance),
        total_distance_km=_round(total_distance / 1000),
        total_work_kj=_round(total_work_kj),
        total_training_load=_round(total_load),
        activities_per_week=_round(_per_week(len(rides), start_dt, end_dt)),
        time_per_week_hours=_round(_per_week(total_duration / 3600, start_dt, end_dt)),
        load_per_week={week: _round(data["load"]) for week, data in weekly.items()},
        duration_hours_per_week={week: _round(data["duration_seconds"] / 3600) for week, data in weekly.items()},
        intensity_distribution=_intensity_distribution(rides),
        recent_load_ramp=_recent_load_ramp(weekly),
        recent_rest_days=_recent_rest_days(rides, end_dt),
        sprint_power=sprint_metrics,
        best_recent_efforts_by_duration=_best_recent_efforts_by_duration(rides),
        wellness_summary=wellness_summary,
        planned_sprint_sessions=sprint_events,
        flags=flags,
        missing_metrics=missing_metrics,
        metadata={
            "source": "intervals_icu",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "notes": [
                "Metrics are reported only when present in Intervals.icu responses.",
                "Flags are transparent heuristics for sprint/kilo planning, not medical advice.",
            ],
        },
    )
    return context.model_dump(mode="json", exclude_none=True)


def _normalize_activity(activity: dict) -> dict:
    start_value = (
        activity.get("start_date_local")
        or activity.get("start_time")
        or activity.get("start_date")
        or activity.get("date")
    )
    start_dt = _parse_datetime(start_value)
    duration = _first_number(activity, ["moving_time", "elapsed_time", "icu_recording_time", "duration"])
    distance = _first_number(activity, ["distance", "icu_distance"])
    work_kj = _first_number(activity, ["work_kj", "kilojoules", "kj"])
    if work_kj is None:
        joules = _first_number(activity, ["icu_joules"])
        work_kj = joules / 1000 if joules is not None else None
    return {
        **activity,
        "id": activity.get("id"),
        "name": activity.get("name"),
        "type": activity.get("type"),
        "start_dt": start_dt,
        "date": _date_string(start_dt),
        "duration_seconds": duration,
        "distance_m": distance,
        "work_kj": work_kj,
        "training_load": _first_number(activity, ["icu_training_load", "training_load"]),
        "intensity": _first_number(activity, ["icu_intensity", "intensity", "intensity_factor"]),
    }


def _is_cycling(activity: dict) -> bool:
    activity_type = str(activity.get("type") or "")
    return activity_type in CYCLING_TYPES or "ride" in activity_type.lower()


def _weekly_rollups(activities: list[dict]) -> dict[str, dict[str, float]]:
    weekly: dict[str, dict[str, float]] = defaultdict(
        lambda: {"activities": 0, "duration_seconds": 0.0, "load": 0.0}
    )
    for activity in activities:
        start_dt = activity.get("start_dt")
        if not start_dt:
            continue
        week = _iso_week(start_dt)
        weekly[week]["activities"] += 1
        weekly[week]["duration_seconds"] += _num(activity.get("duration_seconds")) or 0
        weekly[week]["load"] += _num(activity.get("training_load")) or 0
    return dict(sorted(weekly.items()))


def _sprint_power_metrics(activities: list[dict]) -> tuple[dict[str, Any], list[str]]:
    metrics: dict[str, Any] = {}
    missing: list[str] = []
    for duration in SPRINT_DURATIONS:
        values = []
        for activity in activities:
            value = _power_for_duration(activity, duration)
            if value is not None:
                values.append(
                    {
                        "activity_id": activity.get("id"),
                        "date": activity.get("date"),
                        "name": activity.get("name"),
                        "watts": value,
                    }
                )
        key = f"max_{duration}s_power"
        if values:
            metrics[key] = max(values, key=lambda item: item["watts"])
        else:
            metrics[key] = None
            missing.append(key)
    metrics["trend"] = _sprint_power_trend(activities)
    return metrics, missing


def _power_for_duration(activity: dict, duration: int) -> float | None:
    candidate_keys = [
        f"power_{duration}s",
        f"max_{duration}s_power",
        f"max_power_{duration}s",
        f"best_{duration}s",
        f"p{duration}s",
        f"watts_{duration}s",
    ]
    for key in candidate_keys:
        value = _num(activity.get(key))
        if value is not None:
            return value

    for container_key in ("power_curve", "best_efforts", "efforts"):
        container = activity.get(container_key)
        if isinstance(container, dict):
            value = _num(container.get(str(duration)) or container.get(f"{duration}s"))
            if value is not None:
                return value
        if isinstance(container, list):
            for effort in container:
                if not isinstance(effort, dict):
                    continue
                effort_duration = _num(effort.get("duration") or effort.get("secs"))
                if effort_duration == duration:
                    return _first_number(effort, ["watts", "average", "value", "power"])
    return None


def _sprint_power_trend(activities: list[dict]) -> dict[str, Any]:
    trends: dict[str, Any] = {}
    for duration in (15, 30, 60):
        dated = [
            (activity.get("start_dt"), _power_for_duration(activity, duration))
            for activity in activities
            if activity.get("start_dt") and _power_for_duration(activity, duration) is not None
        ]
        dated.sort(key=lambda item: item[0])
        if len(dated) < 3:
            trends[f"{duration}s"] = None
            continue
        split = max(len(dated) // 2, 1)
        early_best = max(value for _dt, value in dated[:split] if value is not None)
        recent_best = max(value for _dt, value in dated[split:] if value is not None)
        delta = recent_best - early_best
        trends[f"{duration}s"] = {
            "early_best_watts": _round(early_best),
            "recent_best_watts": _round(recent_best),
            "delta_watts": _round(delta),
            "direction": "up" if delta > 0 else "down" if delta < 0 else "flat",
        }
    return trends


def _best_recent_efforts_by_duration(activities: list[dict]) -> dict[str, Any]:
    efforts = {}
    for duration in SPRINT_DURATIONS:
        key = f"{duration}s"
        value = _power_for_duration(max(activities, key=lambda item: _power_for_duration(item, duration) or -1), duration) if activities else None
        efforts[key] = _round(value)
    return efforts


def _wellness_summary(records: list[dict]) -> dict[str, Any] | None:
    if not records:
        return None
    sorted_records = sorted(records, key=lambda item: str(item.get("id") or item.get("date") or ""))
    latest = sorted_records[-1]
    keys = [
        "id",
        "ctl",
        "atl",
        "ctlLoad",
        "atlLoad",
        "restingHR",
        "hrv",
        "hrvSDNN",
        "sleepSecs",
        "sleepScore",
        "sleepQuality",
        "avgSleepingHR",
        "soreness",
        "fatigue",
        "stress",
        "mood",
        "motivation",
    ]
    latest_compact = {key: latest.get(key) for key in keys if key in latest}
    return {
        "records": len(records),
        "date_range": {
            "start": str(sorted_records[0].get("id") or sorted_records[0].get("date")),
            "end": str(latest.get("id") or latest.get("date")),
        },
        "latest": latest_compact,
        "averages": {
            "hrv": _round(_avg(_num(record.get("hrv")) for record in records)),
            "restingHR": _round(_avg(_num(record.get("restingHR")) for record in records)),
            "sleep_hours": _round(_avg((_num(record.get("sleepSecs")) or 0) / 3600 for record in records)),
            "fatigue": _round(_avg(_num(record.get("fatigue")) for record in records)),
            "soreness": _round(_avg(_num(record.get("soreness")) for record in records)),
            "mood": _round(_avg(_num(record.get("mood")) for record in records)),
        },
    }


def _intensity_distribution(activities: list[dict]) -> dict[str, Any] | None:
    power_zone_seconds: list[float] = []
    hr_zone_seconds: list[float] = []
    intensity_values = []
    for activity in activities:
        if isinstance(activity.get("icu_zone_times"), list):
            for index, zone in enumerate(activity["icu_zone_times"]):
                seconds = _zone_seconds(zone)
                if seconds is not None:
                    _extend_to(power_zone_seconds, index)
                    power_zone_seconds[index] += seconds
        if isinstance(activity.get("icu_hr_zone_times"), list):
            for index, seconds in enumerate(activity["icu_hr_zone_times"]):
                seconds_num = _num(seconds)
                if seconds_num is not None:
                    _extend_to(hr_zone_seconds, index)
                    hr_zone_seconds[index] += seconds_num
        intensity = _num(activity.get("intensity"))
        if intensity is not None:
            intensity_values.append(intensity)
    if not power_zone_seconds and not hr_zone_seconds and not intensity_values:
        return None
    return {
        "power_zone_seconds": [_round(value) for value in power_zone_seconds] or None,
        "hr_zone_seconds": [_round(value) for value in hr_zone_seconds] or None,
        "average_intensity": _round(_avg(intensity_values)),
    }


def _cycling_flags(
    activities: list[dict],
    weekly: dict[str, dict[str, float]],
    sprint_metrics: dict[str, Any],
    wellness_summary: dict[str, Any] | None,
    sprint_events: list[dict],
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    ramp = _recent_load_ramp(weekly)
    if ramp and ramp.get("ratio") and ramp["ratio"] >= 1.5:
        flags.append({"type": "high_recent_load", "severity": "medium", "details": ramp})

    hard_days = [
        activity
        for activity in activities
        if (_num(activity.get("training_load")) or 0) >= 75 or (_num(activity.get("intensity")) or 0) >= 0.9
    ]
    if _has_hard_days_close_together(hard_days):
        flags.append(
            {
                "type": "too_many_hard_days_close_together",
                "severity": "medium",
                "note": "Two or more hard cycling days are within 48h.",
            }
        )

    if _has_declining_sprint_power(sprint_metrics):
        flags.append(
            {
                "type": "sprint_power_declining",
                "severity": "medium",
                "note": "Recent sprint-duration bests are below earlier bests in this window.",
            }
        )

    if wellness_summary:
        latest = wellness_summary.get("latest", {})
        ctl = _num(latest.get("ctl"))
        atl = _num(latest.get("atl"))
        fatigue = _num(latest.get("fatigue"))
        if ctl is not None and atl is not None and atl - ctl > 10:
            flags.append(
                {
                    "type": "poor_freshness_before_sprint_work",
                    "severity": "medium",
                    "note": "Latest ATL is more than 10 above CTL.",
                    "ctl": ctl,
                    "atl": atl,
                }
            )
        if fatigue is not None and fatigue >= 4:
            flags.append(
                {
                    "type": "poor_freshness_before_sprint_work",
                    "severity": "medium",
                    "note": "Latest wellness fatigue is high.",
                    "fatigue": fatigue,
                }
            )

    if sprint_events and activities:
        rest_days = {item["date"] for item in _recent_rest_days(activities, activities[-1].get("start_dt"), days=21)}
        for event in sprint_events:
            event_date = _parse_date(event.get("date"))
            if event_date and (event_date - timedelta(days=1)).isoformat() not in rest_days:
                flags.append(
                    {
                        "type": "insufficient_recovery_before_planned_sprint_day",
                        "severity": "medium",
                        "event": event,
                    }
                )
    return flags


def _recent_load_ramp(weekly: dict[str, dict[str, float]]) -> dict[str, Any] | None:
    items = list(weekly.items())
    if len(items) < 3:
        return None
    recent_week, recent = items[-1]
    prior_values = [item[1]["load"] for item in items[:-1] if item[1]["load"] > 0]
    if not prior_values:
        return None
    prior_avg = sum(prior_values[-4:]) / len(prior_values[-4:])
    ratio = recent["load"] / prior_avg if prior_avg else None
    return {
        "week": recent_week,
        "load": _round(recent["load"]),
        "previous_weekly_avg_load": _round(prior_avg),
        "ratio": _round(ratio),
    }


def _recent_rest_days(activities: list[dict], latest: datetime | None, *, days: int = 14) -> list[dict]:
    if not latest:
        return []
    active_dates = {
        activity["start_dt"].date()
        for activity in activities
        if isinstance(activity.get("start_dt"), datetime)
    }
    rest = []
    for offset in range(days):
        day = latest.date() - timedelta(days=offset)
        if day not in active_dates:
            rest.append({"date": day.isoformat(), "days_ago": offset})
    return rest


def _sprint_events(events: list[dict]) -> list[dict]:
    sprint_events = []
    for event in events:
        text = " ".join(str(event.get(key) or "") for key in ("name", "title", "description", "type"))
        if "sprint" not in text.lower() and "30s" not in text.lower() and "60s" not in text.lower():
            continue
        date_value = event.get("start_date_local") or event.get("start_date") or event.get("date")
        sprint_events.append(
            {
                "id": event.get("id"),
                "date": _date_from_value(date_value),
                "name": event.get("name") or event.get("title"),
                "type": event.get("type"),
            }
        )
    return sprint_events


def _has_hard_days_close_together(activities: list[dict]) -> bool:
    dates = sorted(activity["start_dt"] for activity in activities if activity.get("start_dt"))
    return any((later - earlier).total_seconds() <= 48 * 3600 for earlier, later in zip(dates, dates[1:]))


def _has_declining_sprint_power(sprint_metrics: dict[str, Any]) -> bool:
    trend = sprint_metrics.get("trend")
    if not isinstance(trend, dict):
        return False
    return any(isinstance(item, dict) and item.get("direction") == "down" for item in trend.values())


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    dt = _parse_datetime(value)
    if dt:
        return dt.date()
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _date_from_value(value: Any) -> str | None:
    parsed = _parse_date(value)
    return parsed.isoformat() if parsed else None


def _date_string(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def _iso_week(value: datetime) -> str:
    year, week, _weekday = value.isocalendar()
    return f"{year}-W{week:02d}"


def _per_week(value: float, start_dt: datetime | None, end_dt: datetime | None) -> float | None:
    if not start_dt or not end_dt:
        return None
    days = max((end_dt.date() - start_dt.date()).days + 1, 1)
    return value / (days / 7)


def _first_number(data: dict, keys: list[str]) -> float | None:
    for key in keys:
        value = _num(data.get(key))
        if value is not None:
            return value
    return None


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sum_available(values: Any) -> float | None:
    numbers = [_num(value) for value in values]
    filtered = [value for value in numbers if value is not None]
    if not filtered:
        return None
    return sum(filtered)


def _avg(values: Any) -> float | None:
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return sum(filtered) / len(filtered)


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _zone_seconds(zone: Any) -> float | None:
    if isinstance(zone, dict):
        return _first_number(zone, ["secs", "seconds", "duration"])
    return _num(zone)


def _extend_to(values: list[float], index: int) -> None:
    while len(values) <= index:
        values.append(0.0)
