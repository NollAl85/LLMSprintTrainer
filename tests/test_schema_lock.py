from __future__ import annotations

from training_llm_bridge.analytics.cycling_efforts import classify_cycling_activity
from training_llm_bridge.analytics.exposure_calendar import build_daily_exposure_calendar
from training_llm_bridge.analytics.strength_classification import classify_strength_workout
from training_llm_bridge.contexts.combined_context import build_combined_training_context
from training_llm_bridge.contexts.cycling_context import build_cycling_context


def test_schema_lock_for_analytics_outputs() -> None:
    cycling = classify_cycling_activity(
        {
            "id": "a1",
            "name": "Easy",
            "type": "Ride",
            "start_date_local": "2026-01-01T10:00:00",
            "moving_time": 1800,
            "icu_training_load": 10,
        }
    )
    strength = classify_strength_workout(
        {
            "id": "w1",
            "title": "Upper",
            "start_time": "2026-01-01T10:00:00Z",
            "exercises": [{"title": "Push Up", "sets": [{"reps": 5}]}],
        }
    )
    row = build_daily_exposure_calendar([cycling], [strength], {"max_power_watts": {}})[0]

    assert sorted(cycling.keys()) == [
        "activity_id",
        "basis",
        "best_power_watts",
        "cadence_stream_available",
        "date",
        "duration_seconds",
        "evidence",
        "heuristic",
        "missing_metrics",
        "name",
        "near_max_efforts",
        "primary_tag",
        "source",
        "ss_power_model",
        "tags",
    ]
    assert sorted(strength.keys()) == [
        "basis",
        "date",
        "duration_seconds",
        "evidence",
        "exercise_summaries",
        "heuristic",
        "leg_stress",
        "missing_metrics",
        "movement_patterns",
        "primary_session_tag",
        "session_tags",
        "source",
        "title",
        "total_sets",
        "total_volume_kg",
        "uncertainty",
        "workout_id",
    ]
    assert sorted(row.keys()) == [
        "baselines",
        "cycling",
        "date",
        "missing_metrics",
        "strength",
        "wellness",
    ]


def test_schema_lock_for_context_outputs() -> None:
    cycling = build_cycling_context(
        [
            {
                "id": "a1",
                "type": "Ride",
                "start_date_local": "2026-01-01T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 10,
            }
        ]
    )
    combined = build_combined_training_context(lifting_context={"number_of_workouts": 0}, cycling_context=cycling)

    assert "co_occurrences" in cycling
    assert "co_occurrences" in combined
    assert "series" in cycling["sprint_power"]
    assert "trend" not in cycling["sprint_power"]
    assert sorted(combined.keys()) == [
        "co_occurrences",
        "constraints",
        "cross_training_flags",
        "cycling",
        "lifting",
        "metadata",
        "missing_sources",
        "recommendations_ready",
        "wellness",
    ]
