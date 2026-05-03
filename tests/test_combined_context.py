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
                "sets": [{"type": "normal", "weight_kg": 100, "reps": 3, "rpe": 8}],
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
        "icu_training_load": 320,
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
    assert context["cycling"]["co_occurrences"] == []


def test_combined_context_both_sources() -> None:
    context = build_combined_training_context(WORKOUTS, activities=ACTIVITIES, events=EVENTS, weeks=8)

    assert context["lifting"]["number_of_workouts"] == 1
    assert context["cycling"]["number_of_cycling_activities"] == 1
    assert context["missing_sources"] == []
    assert context["cross_training_flags"]
    flag = next(
        flag
        for flag in context["cross_training_flags"]
        if flag["type"] == "hard_leg_lifting_before_key_sprint"
    )
    assert "severity" not in flag
    assert flag["subjective_rating"] == {
        "lifting_session": {"rpe": {"source": "hevy.set_rpe_mean", "value": 8.0}}
    }
    assert context["co_occurrences"] == [
        {
            "iso_week": "2026-W01",
            "flag_types": [
                "hard_leg_lifting_before_key_sprint",
                "lower_body_lifting_in_high_cycling_load_week",
            ],
            "evidence": {
                "lifting_session": {
                    "date": "2026-01-03",
                    "interference_note": (
                        "Heuristic: lower-body lifting may affect sprint quality if placed "
                        "within 24-48h before key sprint work."
                    ),
                    "lower_body_sets": 1,
                    "set_rpe_count": 1,
                    "set_rpe_mean": 8.0,
                    "title": "Lower",
                },
                "sprint_event": {
                    "id": 10,
                    "date": "2026-01-04",
                    "name": "Sprint work",
                    "type": None,
                },
            },
        }
    ]


def test_combined_context_neither_source() -> None:
    context = build_combined_training_context(None, weeks=8)

    assert context["lifting"] is None
    assert context["cycling"] is None
    assert context["recommendations_ready"] is False
    assert context["missing_sources"] == ["hevy", "intervals"]


def test_combined_co_occurrences_require_same_iso_week() -> None:
    context = build_combined_training_context(
        lifting_context={
            "number_of_workouts": 2,
            "lower_body_sprint_interference_flags": [
                {"date": "2026-01-03", "title": "Lower 1", "lower_body_sets": 1},
                {"date": "2026-01-10", "title": "Lower 2", "lower_body_sets": 1},
            ],
        },
        cycling_context={
            "number_of_cycling_activities": 1,
            "planned_sprint_sessions": [{"id": 10, "date": "2026-01-04", "name": "Sprint"}],
            "load_per_week": {"2026-W02": 320},
            "flags": [],
        },
        weeks=2,
    )

    assert len(context["cross_training_flags"]) == 2
    assert context["co_occurrences"] == []
