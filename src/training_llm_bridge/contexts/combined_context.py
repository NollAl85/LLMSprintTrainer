"""Combined Hevy + Intervals.icu training context assembly."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from training_llm_bridge.coach.sprint_constraints import get_sprint_kilo_constraints
from training_llm_bridge.contexts.cycling_context import build_cycling_context
from training_llm_bridge.contexts.lifting_context import build_lifting_context
from training_llm_bridge.contexts.models import CombinedTrainingContext


def build_combined_training_context(
    workouts: list[dict] | None = None,
    *,
    activities: list[dict] | None = None,
    wellness: list[dict] | None = None,
    events: list[dict] | None = None,
    lifting_context: dict | None = None,
    cycling_context: dict | None = None,
    weeks: int | None = None,
) -> dict:
    """Build a combined training context from available lifting and cycling data."""

    missing_sources: list[str] = []

    if lifting_context is None and workouts is not None:
        lifting_context = build_lifting_context(workouts)
    if cycling_context is None and activities is not None:
        cycling_context = build_cycling_context(activities, wellness=wellness, events=events)

    if lifting_context is None:
        missing_sources.append("hevy")
    if cycling_context is None:
        missing_sources.append("intervals")

    wellness_summary = None
    if cycling_context:
        wellness_summary = cycling_context.get("wellness_summary")

    cross_training_flags = _cross_training_flags(lifting_context, cycling_context)
    co_occurrences = _co_occurrences(cross_training_flags)

    combined = CombinedTrainingContext(
        lifting=lifting_context,
        cycling=cycling_context,
        wellness=wellness_summary,
        constraints=get_sprint_kilo_constraints(),
        cross_training_flags=cross_training_flags,
        co_occurrences=co_occurrences,
        recommendations_ready=bool(lifting_context or cycling_context),
        missing_sources=missing_sources,
        metadata={
            "version": "1.1",
            "sources": {
                "lifting": "hevy" if lifting_context is not None else None,
                "cycling": "intervals_icu" if cycling_context is not None else None,
                "wellness": "intervals_icu" if wellness_summary is not None else None,
            },
            "requested_weeks": weeks,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "notes": [
                "Cross-training flags are heuristic and transparent.",
                "Sprint/kilo cycling quality is treated as the primary objective.",
                "Intervals.icu remains read-only in v1.1.",
            ],
        },
    )
    return combined.model_dump(mode="json")


def _cross_training_flags(
    lifting: dict[str, Any] | None, cycling: dict[str, Any] | None
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if not lifting or not cycling:
        return flags

    lower_body_sessions = lifting.get("lower_body_sprint_interference_flags") or []
    planned_sprints = cycling.get("planned_sprint_sessions") or []
    cycling_flags = cycling.get("flags") or []
    weekly_load = cycling.get("load_per_week") or {}

    for session in lower_body_sessions:
        session_date = _parse_date(session.get("date"))
        if not session_date:
            continue
        for event in planned_sprints:
            event_date = _parse_date(event.get("date"))
            if not event_date:
                continue
            hours_before = (event_date - session_date).days * 24
            if 0 <= hours_before <= 48:
                flags.append(
                    {
                        "basis": "lower-body lifting date is within 24-48h before planned sprint event",
                        "heuristic": True,
                        "type": "hard_leg_lifting_before_key_sprint",
                        "lifting_session": session,
                        "sprint_event": event,
                        "note": "Heuristic: lower-body lifting within 24-48h may compromise sprint quality.",
                        "subjective_rating": {"lifting_session": _lifting_subjective_rating(session)},
                    }
                )

    high_load_weeks = {
        week for week, load in weekly_load.items() if isinstance(load, (int, float)) and load >= 300
    }
    for session in lower_body_sessions:
        session_date = _parse_date(session.get("date"))
        if session_date and _iso_week_from_date(session_date) in high_load_weeks:
            flags.append(
                {
                    "basis": "lower-body lifting occurred in a week with high cycling load",
                    "heuristic": True,
                    "type": "lower_body_lifting_in_high_cycling_load_week",
                    "lifting_session": session,
                    "note": "Heuristic: lower-body strength work may need lower volume in high cycling load weeks.",
                    "subjective_rating": {"lifting_session": _lifting_subjective_rating(session)},
                }
            )

    sprint_event_weeks: dict[str, int] = {}
    for event in planned_sprints:
        event_date = _parse_date(event.get("date"))
        if event_date:
            week = _iso_week_from_date(event_date)
            sprint_event_weeks[week] = sprint_event_weeks.get(week, 0) + 1
    for week, count in sprint_event_weeks.items():
        sessions_in_week = [
            session
            for session in lower_body_sessions
            if _parse_date(session.get("date"))
            and _iso_week_from_date(_parse_date(session.get("date"))) == week
        ]
        lower_sets = sum(
            int(session.get("lower_body_sets") or 0)
            for session in sessions_in_week
        )
        if count >= 2 and lower_sets >= 8:
            flags.append(
                {
                    "basis": "multiple planned sprint sessions and lower-body set count in the same ISO week",
                    "heuristic": True,
                    "type": "too_much_lower_body_volume_in_multi_sprint_week",
                    "week": week,
                    "planned_sprint_sessions": count,
                    "lower_body_sets": lower_sets,
                    "lifting_sessions": sessions_in_week,
                    "subjective_rating": {
                        "lifting_session": _aggregate_lifting_subjective_rating(sessions_in_week)
                    },
                }
            )

    recovery_flags = [
        flag
        for flag in cycling_flags
        if flag.get("type") == "insufficient_recovery_before_planned_sprint_day"
    ]
    if recovery_flags:
        flags.append(
            {
                "basis": "cycling context reported insufficient recovery around planned sprint work",
                "heuristic": True,
                "type": "preserve_recovery_after_maximal_sprint_work",
                "note": "No obvious recovery day was found around planned sprint work.",
                "cycling_flag": recovery_flags[0],
                "event": recovery_flags[0].get("event"),
                "subjective_rating": recovery_flags[0].get(
                    "subjective_rating", {"cycling_session": None}
                ),
            }
        )

    return flags


def _parse_date(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return datetime.fromisoformat(str(value)[:10]).date()
        except ValueError:
            return None


def _iso_week_from_date(value) -> str:
    year, week, _weekday = value.isocalendar()
    return f"{year}-W{week:02d}"


def _lifting_subjective_rating(session: dict[str, Any]) -> dict[str, Any] | None:
    value = _num(session.get("set_rpe_mean"))
    if value is None:
        return None
    return {"rpe": {"source": "hevy.set_rpe_mean", "value": round(value, 2)}}


def _aggregate_lifting_subjective_rating(sessions: list[dict[str, Any]]) -> dict[str, Any] | None:
    values = [_num(session.get("set_rpe_mean")) for session in sessions]
    filtered = [value for value in values if value is not None]
    if not filtered:
        return None
    return {"rpe": {"source": "hevy.set_rpe_mean", "value": round(sum(filtered) / len(filtered), 2)}}


def _num(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _co_occurrences(flags: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for flag in flags:
        week = _flag_iso_week(flag)
        if week:
            grouped.setdefault(week, []).append(flag)

    output = []
    for week, week_flags in grouped.items():
        flag_types = sorted({str(flag.get("type")) for flag in week_flags if flag.get("type")})
        if len(flag_types) < 2:
            continue
        evidence: dict[str, Any] = {}
        for flag in week_flags:
            _merge_evidence(evidence, _flag_evidence(flag))
        output.append({"iso_week": week, "flag_types": flag_types, "evidence": evidence})
    return sorted(output, key=lambda item: item["iso_week"])


def _flag_iso_week(flag: dict[str, Any]) -> str | None:
    for path in (
        ("lifting_session", "date"),
        ("cycling_session", "date"),
        ("event", "date"),
        ("sprint_event", "date"),
    ):
        value = flag.get(path[0])
        if isinstance(value, dict):
            parsed = _parse_date(value.get(path[1]))
            if parsed:
                return _iso_week_from_date(parsed)
    if flag.get("week"):
        return str(flag["week"])
    parsed = _parse_date(flag.get("date"))
    return _iso_week_from_date(parsed) if parsed else None


def _flag_evidence(flag: dict[str, Any]) -> dict[str, Any]:
    excluded = {"basis", "heuristic", "note", "subjective_rating", "type"}
    return {key: value for key, value in flag.items() if key not in excluded}


def _merge_evidence(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if key not in target:
            target[key] = value
        elif target[key] != value:
            existing = target[key] if isinstance(target[key], list) else [target[key]]
            if value not in existing:
                existing.append(value)
            target[key] = existing
