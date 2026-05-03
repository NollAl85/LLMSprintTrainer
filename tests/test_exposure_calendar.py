from __future__ import annotations

from training_llm_bridge.analytics.exposure_calendar import (
    build_daily_exposure_calendar,
    build_weekly_exposure_summary,
)


def test_one_row_per_input_date_and_merge() -> None:
    cycling = [
        {
            "activity_id": "a1",
            "date": "2026-01-01",
            "duration_seconds": 1200,
            "evidence": {"start_time": "2026-01-01T09:00:00", "training_load": 25},
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
            "leg_stress": {
                "heuristic": True,
                "basis": "movement-pattern set counts and tracked load; practical heuristic, not a physiology score",
                "overall": {"sets": 3, "stress": "low", "volume_kg": 900},
                "posterior_chain": {
                    "exercises": [],
                    "movement_patterns": ["hinge_pattern", "hamstring_eccentric"],
                    "sets": 0,
                    "stress": "none",
                    "volume_kg": 0,
                },
                "quads": {
                    "exercises": ["Squat"],
                    "movement_patterns": ["squat_pattern", "unilateral_leg"],
                    "sets": 3,
                    "stress": "low",
                    "volume_kg": 900,
                },
            },
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
    assert rows[0]["strength"]["leg_stress"]["quads"]["sets"] == 3
    assert rows[1]["wellness"]["ctl"] == 50


def test_weekly_summary_totals_ss_power_model_fields() -> None:
    cycling = [
        {
            "activity_id": "a1",
            "date": "2026-01-01",
            "duration_seconds": 1200,
            "evidence": {"start_time": "2026-01-01T07:00:00", "training_load": 25},
            "best_power_watts": {},
            "near_max_efforts": {},
            "primary_tag": "pmax_sprint",
            "ss_power_model": {"ss_cp": 10.25, "ss_p_max": 2.5, "ss_w_prime": 1.25},
            "tags": ["pmax_sprint"],
            "missing_metrics": [],
        },
        {
            "activity_id": "a2",
            "date": "2026-01-01",
            "duration_seconds": 1800,
            "evidence": {"start_time": "2026-01-01T17:00:00", "training_load": 35},
            "best_power_watts": {},
            "near_max_efforts": {},
            "primary_tag": "pmax_sprint",
            "ss_power_model": {"ss_cp": 20.25, "ss_p_max": 3.5, "ss_w_prime": 2.25},
            "tags": ["pmax_sprint"],
            "missing_metrics": [],
        },
    ]

    rows = build_daily_exposure_calendar(cycling, [], {}, wellness=None)
    summary = build_weekly_exposure_summary(rows)

    assert rows[0]["cycling"]["ss_power_model"]["latest"]["activity_id"] == "a2"
    assert summary[0]["week"] == "2026-W01"
    assert summary[0]["cycling"]["activity_count"] == 2
    assert summary[0]["cycling"]["duration_seconds"] == 3000
    assert summary[0]["cycling"]["training_load"] == 60
    assert summary[0]["cycling"]["ss_power_model_totals"]["records_count"] == 2
    assert summary[0]["cycling"]["ss_power_model_totals"]["ss_cp"] == 30.5
    assert summary[0]["cycling"]["ss_power_model_totals"]["ss_p_max"] == 6.0
    assert summary[0]["cycling"]["ss_power_model_totals"]["ss_w_prime"] == 3.5


def test_missing_wellness_handled() -> None:
    rows = build_daily_exposure_calendar(
        classified_cycling=[{"activity_id": "a1", "date": "2026-01-01", "missing_metrics": []}],
        classified_strength=[],
        baselines={},
        wellness=None,
    )

    assert rows[0]["wellness"]["missing_metrics"] == ["wellness"]
