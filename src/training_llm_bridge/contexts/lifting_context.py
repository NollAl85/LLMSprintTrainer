"""Build compact lifting analytics from Hevy workout dictionaries."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from training_llm_bridge.contexts.models import LiftingContext

LOWER_BODY_KEYWORDS = {
    "label": "heuristic_lower_body_keywords",
    "keywords": [
        "squat",
        "deadlift",
        "lunge",
        "leg press",
        "leg curl",
        "leg extension",
        "calf",
        "hip thrust",
        "glute",
        "good morning",
        "romanian deadlift",
    ],
}

MAJOR_LIFT_KEYWORDS = [
    "squat",
    "deadlift",
    "bench press",
    "overhead press",
    "military press",
    "row",
    "pull up",
    "chin up",
    "hip thrust",
    "leg press",
    "romanian deadlift",
    "front squat",
]


def build_lifting_context(workouts: list[dict]) -> dict:
    """Build a compact JSON-serializable lifting context from Hevy workouts."""

    normalized = [_normalize_workout(workout) for workout in workouts]
    normalized.sort(key=lambda item: item["start_dt"] or datetime.min.replace(tzinfo=timezone.utc))

    dated = [workout for workout in normalized if workout["start_dt"] is not None]
    start_dt = dated[0]["start_dt"] if dated else None
    end_dt = dated[-1]["start_dt"] if dated else None

    total_sets = 0
    total_volume = 0.0
    exercises_seen: set[str] = set()
    sets_per_exercise: dict[str, int] = defaultdict(int)
    volume_per_exercise: dict[str, float] = defaultdict(float)
    best_1rm: dict[str, dict[str, Any]] = {}
    top_sets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    exposure_dates: dict[str, list[datetime]] = defaultdict(list)
    dated_performances: dict[str, list[dict[str, Any]]] = defaultdict(list)
    weekly_volume: dict[str, float] = defaultdict(float)
    lower_body_sessions: list[dict[str, Any]] = []
    workout_summaries: list[dict[str, Any]] = []

    for workout in normalized:
        workout_sets = 0
        workout_volume = 0.0
        workout_exercises: list[str] = []
        lower_body_sets = 0
        workout_rpe_values: list[float] = []

        for exercise in workout["exercises"]:
            title = exercise["title"]
            if not title:
                continue
            exercises_seen.add(title)
            workout_exercises.append(title)
            if workout["start_dt"]:
                exposure_dates[title].append(workout["start_dt"])

            for set_item in exercise["sets"]:
                rpe = _as_float(set_item.get("rpe"))
                if rpe is not None:
                    workout_rpe_values.append(rpe)
                total_sets += 1
                workout_sets += 1
                sets_per_exercise[title] += 1
                if _is_lower_body_exercise(title):
                    lower_body_sets += 1

                volume = _set_volume(set_item)
                total_volume += volume
                workout_volume += volume
                volume_per_exercise[title] += volume

                estimated_1rm = _estimated_1rm(set_item)
                top_set = {
                    "date": _date_string(workout["start_dt"]),
                    "workout_id": workout["id"],
                    "weight_kg": _as_float(set_item.get("weight_kg")),
                    "reps": _as_float(set_item.get("reps")),
                    "estimated_1rm_kg": _round(estimated_1rm),
                    "volume_kg": _round(volume),
                }
                top_sets[title].append(top_set)
                if estimated_1rm is not None:
                    current = best_1rm.get(title)
                    if current is None or estimated_1rm > current["estimated_1rm_kg"]:
                        best_1rm[title] = {**top_set, "estimated_1rm_kg": _round(estimated_1rm)}

                if workout["start_dt"]:
                    dated_performances[title].append(
                        {
                            "date": workout["start_dt"],
                            "estimated_1rm_kg": estimated_1rm,
                            "volume_kg": volume,
                            "weight_kg": _as_float(set_item.get("weight_kg")),
                            "reps": _as_float(set_item.get("reps")),
                        }
                    )

        if workout["start_dt"]:
            weekly_volume[_iso_week(workout["start_dt"])] += workout_volume

        if lower_body_sets:
            lower_body_sessions.append(
                {
                    "date": _date_string(workout["start_dt"]),
                    "title": workout["title"],
                    "lower_body_sets": lower_body_sets,
                    "set_rpe_mean": _round(_avg(workout_rpe_values)),
                    "set_rpe_count": len(workout_rpe_values),
                    "interference_note": (
                        "Heuristic: lower-body lifting may affect sprint quality if placed "
                        "within 24-48h before key sprint work."
                    ),
                }
            )

        workout_summaries.append(
            {
                "id": workout["id"],
                "title": workout["title"],
                "start_time": workout["start_time"],
                "total_sets": workout_sets,
                "total_volume_kg": _round(workout_volume),
                "set_rpe_mean": _round(_avg(workout_rpe_values)),
                "exercises": sorted(set(workout_exercises)),
            }
        )

    context = LiftingContext(
        number_of_workouts=len(workouts),
        date_range={
            "start": _date_string(start_dt),
            "end": _date_string(end_dt),
        },
        workouts_per_week=_round(_workouts_per_week(len(workouts), start_dt, end_dt)),
        total_sets=total_sets,
        total_volume_kg=_round(total_volume),
        exercises_performed=sorted(exercises_seen),
        metadata={
            "source": "hevy",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "heuristics": [LOWER_BODY_KEYWORDS],
        },
    ).model_dump(mode="json")

    context.update(
        {
            "sets_per_exercise": dict(sorted(sets_per_exercise.items())),
            "volume_per_exercise_kg": {
                key: _round(value) for key, value in sorted(volume_per_exercise.items())
            },
            "top_sets_per_exercise": _compact_top_sets(top_sets),
            "estimated_1rm_kg": {
                key: value for key, value in sorted(best_1rm.items(), key=lambda item: item[0])
            },
            "recent_progression_major_lifts": _recent_progression(dated_performances),
            "exercises_not_trained_recently": _not_trained_recently(exposure_dates, end_dt),
            "stalled_exercises": _stalled_exercises(dated_performances),
            "sudden_volume_spikes": _volume_spikes(weekly_volume),
            "high_frequency_exercise_patterns": _high_frequency_patterns(exposure_dates, end_dt),
            "lower_body_sprint_interference_flags": lower_body_sessions[-6:],
            "workout_summaries": workout_summaries[-12:],
        }
    )
    return context


def _normalize_workout(workout: dict) -> dict:
    data = workout.get("workout", workout)
    start_time = data.get("start_time") or data.get("workout_start_time")
    return {
        "id": data.get("id"),
        "title": data.get("title"),
        "start_time": start_time,
        "end_time": data.get("end_time") or data.get("workout_end_time"),
        "start_dt": _parse_datetime(start_time),
        "exercises": [_normalize_exercise(item) for item in data.get("exercises", [])],
    }


def _normalize_exercise(exercise: dict) -> dict:
    return {
        "title": exercise.get("title") or exercise.get("name") or "",
        "exercise_template_id": exercise.get("exercise_template_id"),
        "sets": list(exercise.get("sets") or []),
    }


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _date_string(value: datetime | None) -> str | None:
    return value.date().isoformat() if value else None


def _workouts_per_week(count: int, start_dt: datetime | None, end_dt: datetime | None) -> float | None:
    if count == 0:
        return 0.0
    if not start_dt or not end_dt:
        return None
    days = max((end_dt.date() - start_dt.date()).days + 1, 1)
    return count / (days / 7)


def _set_volume(set_item: dict) -> float:
    weight = _as_float(set_item.get("weight_kg"))
    reps = _as_float(set_item.get("reps"))
    if weight is None or reps is None:
        return 0.0
    return max(weight, 0) * max(reps, 0)


def _estimated_1rm(set_item: dict) -> float | None:
    weight = _as_float(set_item.get("weight_kg"))
    reps = _as_float(set_item.get("reps"))
    if weight is None or reps is None or weight <= 0 or reps <= 0 or reps > 12:
        return None
    if reps == 1:
        return weight
    return weight * (1 + reps / 30)


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _compact_top_sets(top_sets: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    compact: dict[str, list[dict[str, Any]]] = {}
    for title, sets in top_sets.items():
        compact[title] = sorted(
            sets,
            key=lambda item: (
                item["estimated_1rm_kg"] is not None,
                item["estimated_1rm_kg"] or 0,
                item["volume_kg"] or 0,
            ),
            reverse=True,
        )[:3]
    return dict(sorted(compact.items()))


def _recent_progression(dated_performances: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    progression: dict[str, dict[str, Any]] = {}
    for title, performances in dated_performances.items():
        if not _is_major_lift(title):
            continue
        best_by_day = _best_1rm_by_day(performances)
        if len(best_by_day) < 2:
            continue
        split = max(len(best_by_day) // 2, 1)
        early_best = max(item["estimated_1rm_kg"] for item in best_by_day[:split])
        recent_best = max(item["estimated_1rm_kg"] for item in best_by_day[split:])
        delta = recent_best - early_best
        progression[title] = {
            "early_best_estimated_1rm_kg": _round(early_best),
            "recent_best_estimated_1rm_kg": _round(recent_best),
            "delta_kg": _round(delta),
        }
    return dict(sorted(progression.items()))


def _best_1rm_by_day(performances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_day: dict[str, float] = {}
    for performance in performances:
        est = performance.get("estimated_1rm_kg")
        if est is None:
            continue
        day = performance["date"].date().isoformat()
        by_day[day] = max(by_day.get(day, 0), est)
    return [
        {"date": day, "estimated_1rm_kg": value}
        for day, value in sorted(by_day.items(), key=lambda item: item[0])
    ]


def _not_trained_recently(
    exposure_dates: dict[str, list[datetime]], latest: datetime | None, threshold_days: int = 21
) -> list[dict[str, Any]]:
    if not latest:
        return []
    stale = []
    for title, dates in exposure_dates.items():
        last = max(dates)
        days = (latest.date() - last.date()).days
        if days >= threshold_days:
            stale.append({"exercise": title, "last_trained": _date_string(last), "days_since": days})
    return sorted(stale, key=lambda item: item["days_since"], reverse=True)[:12]


def _stalled_exercises(dated_performances: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    stalled = []
    for title, performances in dated_performances.items():
        best_by_day = _best_1rm_by_day(performances)
        if len(best_by_day) < 3:
            continue
        recent = best_by_day[-2:]
        previous = best_by_day[:-2]
        previous_best = max(item["estimated_1rm_kg"] for item in previous)
        recent_best = max(item["estimated_1rm_kg"] for item in recent)
        if recent_best <= previous_best * 1.01:
            stalled.append(
                {
                    "exercise": title,
                    "previous_best_estimated_1rm_kg": _round(previous_best),
                    "recent_best_estimated_1rm_kg": _round(recent_best),
                    "note": "Heuristic: recent top estimated 1RM is not clearly above prior best.",
                }
            )
    return sorted(stalled, key=lambda item: item["exercise"])[:12]


def _volume_spikes(weekly_volume: dict[str, float]) -> list[dict[str, Any]]:
    weeks = sorted(weekly_volume.items(), key=lambda item: item[0])
    if len(weeks) < 3:
        return []
    spikes = []
    for index in range(2, len(weeks)):
        week, volume = weeks[index]
        prior = [item[1] for item in weeks[max(0, index - 4) : index]]
        prior_avg = sum(prior) / len(prior)
        if prior_avg > 0 and volume > prior_avg * 1.5:
            spikes.append(
                {
                    "week": week,
                    "volume_kg": _round(volume),
                    "previous_weekly_avg_kg": _round(prior_avg),
                    "ratio": _round(volume / prior_avg),
                }
            )
    return spikes[-8:]


def _high_frequency_patterns(
    exposure_dates: dict[str, list[datetime]], latest: datetime | None
) -> list[dict[str, Any]]:
    if not latest:
        return []
    window_start = latest - timedelta(days=6)
    patterns = []
    for title, dates in exposure_dates.items():
        distinct_days = {date.date().isoformat() for date in dates if date >= window_start}
        if len(distinct_days) >= 3:
            patterns.append(
                {
                    "exercise": title,
                    "sessions_last_7_days": len(distinct_days),
                    "note": "High frequency can be useful, but watch joint stress and sprint freshness.",
                }
            )
    return sorted(patterns, key=lambda item: item["sessions_last_7_days"], reverse=True)


def _is_major_lift(title: str) -> bool:
    lower = title.lower()
    return any(keyword in lower for keyword in MAJOR_LIFT_KEYWORDS)


def _is_lower_body_exercise(title: str) -> bool:
    lower = title.lower()
    return any(keyword in lower for keyword in LOWER_BODY_KEYWORDS["keywords"])


def _iso_week(value: datetime) -> str:
    year, week, _weekday = value.isocalendar()
    return f"{year}-W{week:02d}"
