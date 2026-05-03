from __future__ import annotations

from training_llm_bridge.contexts.combined_context import build_combined_training_context
from training_llm_bridge.contexts.lifting_context import build_lifting_context


WORKOUTS = [
    {
        "id": "w1",
        "title": "Lower 1",
        "start_time": "2026-01-01T10:00:00Z",
        "exercises": [
            {
                "title": "Squat (Barbell)",
                "exercise_template_id": "D04AC939",
                "sets": [
                    {"type": "normal", "weight_kg": 100, "reps": 5},
                    {"type": "normal", "weight_kg": 105, "reps": 3},
                ],
            },
            {
                "title": "Bench Press (Barbell)",
                "exercise_template_id": "79D0BB3A",
                "sets": [{"type": "normal", "weight_kg": 80, "reps": 5}],
            },
        ],
    },
    {
        "id": "w2",
        "title": "Lower 2",
        "start_time": "2026-01-08T10:00:00Z",
        "exercises": [
            {
                "title": "Squat (Barbell)",
                "exercise_template_id": "D04AC939",
                "sets": [
                    {"type": "normal", "weight_kg": 110, "reps": 5},
                    {"type": "normal", "weight_kg": 112.5, "reps": 3},
                ],
            }
        ],
    },
]


def test_lifting_context_computes_volume_and_progression() -> None:
    context = build_lifting_context(WORKOUTS)

    assert context["number_of_workouts"] == 2
    assert context["date_range"] == {"start": "2026-01-01", "end": "2026-01-08"}
    assert context["total_sets"] == 5
    assert context["total_volume_kg"] == 2102.5
    assert context["sets_per_exercise"]["Squat (Barbell)"] == 4
    assert context["volume_per_exercise_kg"]["Squat (Barbell)"] == 1702.5
    assert context["estimated_1rm_kg"]["Squat (Barbell)"]["estimated_1rm_kg"] == 128.33
    assert context["recent_progression_major_lifts"]["Squat (Barbell)"]["direction"] == "up"
    assert context["lower_body_sprint_interference_flags"]


def test_combined_context_shape() -> None:
    context = build_combined_training_context(WORKOUTS, weeks=8)

    assert context["lifting"]["number_of_workouts"] == 2
    assert context["cycling"] is None
    assert context["wellness"] is None
    assert context["recommendations_ready"] is True
    assert context["constraints"]["sport_context"] == "cycling sprint and kilo performance"
    assert context["metadata"]["requested_weeks"] == 8
