from __future__ import annotations

from training_llm_bridge.analytics.exposure_calendar import build_daily_exposure_calendar


def test_one_row_per_input_date_and_merge() -> None:
    cycling = [
        {
            "activity_id": "a1",
            "date": "2026-01-01",
            "duration_seconds": 1200,
            "evidence": {"training_load": 25},
            "best_power_watts": {"5": 900},
            "near_max_efforts": {"5": 1},
            "primary_tag": "pmax_sprint",
            "ss_power_model": {"ss_cp": 50.5, "ss_p_max": 11.0, "ss_w_prime": 3.0},
            "tags": ["pmax_sprint"],
            "missing_metrics": ["cadence_stream"],
        }
    ]
    strength = [
        {
            "workout_id": "w1",
            "date": "2026-01-01",
            "total_sets": 3,
            "total_volume_kg": 900,
            "primary_session_tag": "max_strength",
            "session_tags": ["max_strength", "lower_body"],
            "movement_patterns": {"squat_pattern": {"sets": 3, "volume_kg": 900, "exercises": ["Squat"]}},
            "missing_metrics": ["rpe"],
            "uncertainty": ["RPE absent"],
        }
    ]
    wellness = [{"id": "2026-01-02", "ctl": 50}]

    rows = build_daily_exposure_calendar(cycling, strength, {"max_power_watts": {"5": 900}}, wellness)

    assert [row["date"] for row in rows] == ["2026-01-01", "2026-01-02"]
    assert rows[0]["cycling"]["activity_count"] == 1
    assert rows[0]["cycling"]["ss_power_model"]["latest"]["ss_cp"] == 50.5
    assert rows[0]["strength"]["workout_count"] == 1
    assert rows[1]["wellness"]["ctl"] == 50


def test_missing_wellness_handled() -> None:
    rows = build_daily_exposure_calendar(
        classified_cycling=[{"activity_id": "a1", "date": "2026-01-01", "missing_metrics": []}],
        classified_strength=[],
        baselines={},
        wellness=None,
    )

    assert rows[0]["wellness"]["missing_metrics"] == ["wellness"]
