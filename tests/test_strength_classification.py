from __future__ import annotations

from training_llm_bridge.analytics.strength_classification import classify_strength_workout


def test_lower_body_max_strength_session() -> None:
    workout = {
        "id": "w1",
        "title": "Heavy lower",
        "start_time": "2026-01-01T10:00:00Z",
        "exercises": [
            {
                "title": "Back Squat",
                "sets": [
                    {"weight_kg": 140, "reps": 3},
                    {"weight_kg": 145, "reps": 3},
                    {"weight_kg": 150, "reps": 2},
                ],
            }
        ],
    }

    result = classify_strength_workout(workout)

    assert result["primary_session_tag"] == "max_strength"
    assert "lower_body" in result["session_tags"]
    assert result["movement_patterns"]["squat_pattern"]["sets"] == 3


def test_lower_body_hypertrophy_session() -> None:
    workout = {
        "id": "w2",
        "title": "Leg volume",
        "start_time": "2026-01-02T10:00:00Z",
        "exercises": [
            {"title": "Bulgarian Split Squat", "sets": [{"weight_kg": 20, "reps": 10}] * 3},
            {"title": "Leg Press", "sets": [{"weight_kg": 120, "reps": 12}] * 3},
        ],
    }

    result = classify_strength_workout(workout)

    assert "hypertrophy" in result["session_tags"]
    assert "lower_body" in result["session_tags"]
    assert result["movement_patterns"]["unilateral_leg"]["sets"] == 3


def test_upper_only_session() -> None:
    workout = {
        "id": "w3",
        "title": "Upper",
        "start_time": "2026-01-03T10:00:00Z",
        "exercises": [
            {"title": "Bench Press (Barbell)", "sets": [{"weight_kg": 80, "reps": 5}] * 3},
            {"title": "Row (Dumbbell)", "sets": [{"weight_kg": 30, "reps": 8}] * 3},
        ],
    }

    result = classify_strength_workout(workout)

    assert "upper_body" in result["session_tags"]
    assert result["movement_patterns"]["upper_push"]["sets"] == 3
    assert result["movement_patterns"]["upper_pull"]["sets"] == 3


def test_unknown_exercise_produces_uncertainty() -> None:
    workout = {
        "id": "w4",
        "title": "Odd",
        "start_time": "2026-01-04T10:00:00Z",
        "exercises": [{"title": "Mystery Drill", "sets": [{"reps": 7}]}],
    }

    result = classify_strength_workout(workout)

    assert result["movement_patterns"]["unknown"]["sets"] == 1
    assert any("Mystery Drill" in item for item in result["uncertainty"])
