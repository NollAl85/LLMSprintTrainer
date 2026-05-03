from __future__ import annotations

from training_llm_bridge.contexts.combined_context import build_combined_training_context


WORKOUTS = [
    {
        "id": "w1",
        "title": "Lower",
        "start_time": "2026-01-03T10:00:00Z",
        "exercises": [
            {
                "title": "Squat (Barbell)",
                "sets": [{"type": "normal", "weight_kg": 100, "reps": 3}],
            }
        ],
    }
]

ACTIVITIES = [
    {
        "id": "a1",
        "name": "Sprint session",
        "type": "Ride",
        "start_date_local": "2026-01-04T10:00:00",
        "moving_time": 3600,
        "icu_training_load": 85,
        "power_30s": 700,
        "power_60s": 550,
    }
]

EVENTS = [{"id": 10, "name": "Sprint work", "start_date_local": "2026-01-04T09:00:00"}]


def test_combined_context_hevy_only() -> None:
    context = build_combined_training_context(WORKOUTS, weeks=8)

    assert context["lifting"]["number_of_workouts"] == 1
    assert context["cycling"] is None
    assert context["missing_sources"] == ["intervals"]


def test_combined_context_intervals_only() -> None:
    context = build_combined_training_context(None, activities=ACTIVITIES, events=EVENTS, weeks=8)

    assert context["lifting"] is None
    assert context["cycling"]["number_of_cycling_activities"] == 1
    assert context["missing_sources"] == ["hevy"]


def test_combined_context_both_sources() -> None:
    context = build_combined_training_context(WORKOUTS, activities=ACTIVITIES, events=EVENTS, weeks=8)

    assert context["lifting"]["number_of_workouts"] == 1
    assert context["cycling"]["number_of_cycling_activities"] == 1
    assert context["missing_sources"] == []
    assert context["cross_training_flags"]


def test_combined_context_neither_source() -> None:
    context = build_combined_training_context(None, weeks=8)

    assert context["lifting"] is None
    assert context["cycling"] is None
    assert context["recommendations_ready"] is False
    assert context["missing_sources"] == ["hevy", "intervals"]
