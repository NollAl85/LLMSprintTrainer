from __future__ import annotations

from training_llm_bridge.contexts.cycling_context import build_cycling_context


ACTIVITIES = [
    {
        "id": "a1",
        "name": "Sprint ride",
        "type": "Ride",
        "start_date_local": "2026-01-01T10:00:00",
        "moving_time": 3600,
        "distance": 30000,
        "icu_joules": 600000,
        "icu_training_load": 70,
        "icu_intensity": 0.92,
        "perceived_exertion": 7,
        "feel": 4,
        "power_5s": 900,
        "power_15s": 780,
        "power_30s": 650,
        "power_60s": 520,
        "ss_cp": 50.51385,
        "ss_p_max": 11.039366,
        "ss_w_prime": 3.0405822,
    },
    {
        "id": "a2",
        "name": "Endurance",
        "type": "VirtualRide",
        "start_date_local": "2026-01-08T10:00:00",
        "moving_time": 5400,
        "distance": 42000,
        "icu_joules": 800000,
        "icu_training_load": 90,
        "icu_intensity": 0.7,
        "feel": 3,
        "power_5s": 850,
        "power_15s": 730,
        "power_30s": 610,
        "power_60s": 500,
    },
]

WELLNESS = [
    {"id": "2026-01-08", "ctl": 60, "atl": 66, "hrv": 55, "restingHR": 44, "sleepSecs": 28800}
]


def test_cycling_context_computes_basic_weekly_load_and_duration() -> None:
    context = build_cycling_context(ACTIVITIES, wellness=WELLNESS)

    assert context["number_of_cycling_activities"] == 2
    assert context["total_duration_seconds"] == 9000
    assert context["total_duration_hours"] == 2.5
    assert context["total_distance_km"] == 72
    assert context["total_work_kj"] == 1400
    assert context["total_training_load"] == 160
    assert context["load_per_week"] == {"2026-W01": 70.0, "2026-W02": 90.0}
    assert context["sprint_power"]["max_5s_power"]["watts"] == 900
    assert context["sprint_power"]["series"]["30s"] == [
        {"activity_id": "a1", "date": "2026-01-01", "watts": 650},
        {"activity_id": "a2", "date": "2026-01-08", "watts": 610},
    ]
    assert context["ss_power_model"]["latest"]["ss_cp"] == 50.51
    assert context["ss_power_model"]["latest"]["ss_p_max"] == 11.04
    assert context["ss_power_model"]["latest"]["ss_w_prime"] == 3.04
    assert context["wellness_summary"]["latest"]["ctl"] == 60
    assert "intervals_subjective" not in context["missing_metrics"]


def test_missing_sprint_power_metrics_are_handled_gracefully() -> None:
    context = build_cycling_context(
        [{"id": "a3", "type": "Ride", "start_date_local": "2026-01-01", "moving_time": 1800}]
    )

    assert context["sprint_power"]["max_5s_power"] is None
    assert "max_5s_power" in context["missing_metrics"]
    assert "intervals_subjective" in context["missing_metrics"]
    assert context["ss_power_model"]["latest"] is None
    assert "ss_cp" in context["missing_metrics"]


def test_cycling_subjective_rating_uses_perceived_exertion_and_feel() -> None:
    context = build_cycling_context(
        [
            {
                "id": "a1",
                "type": "Ride",
                "start_date_local": "2026-01-01T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
            },
            {
                "id": "a2",
                "type": "Ride",
                "start_date_local": "2026-01-02T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
                "perceived_exertion": 7,
                "feel": 4,
            },
        ]
    )

    flag = next(flag for flag in context["flags"] if flag["type"] == "too_many_hard_days_close_together")

    assert "severity" not in flag
    assert flag["subjective_rating"] == {
        "cycling_session": {
            "rpe": {"source": "intervals.perceived_exertion", "value": 7.0},
            "feel": {"source": "intervals.feel", "value": 4.0},
        }
    }
    assert "intervals_subjective" in context["missing_metrics"]


def test_cycling_subjective_rating_with_only_feel_is_not_missing() -> None:
    context = build_cycling_context(
        [
            {
                "id": "a1",
                "type": "Ride",
                "start_date_local": "2026-01-01T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
            },
            {
                "id": "a2",
                "type": "Ride",
                "start_date_local": "2026-01-02T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
                "feel": 3,
            },
        ]
    )

    flag = next(flag for flag in context["flags"] if flag["type"] == "too_many_hard_days_close_together")

    assert flag["subjective_rating"] == {
        "cycling_session": {"rpe": None, "feel": {"source": "intervals.feel", "value": 3.0}}
    }


def test_cycling_subjective_rating_missing_session_is_null() -> None:
    context = build_cycling_context(
        [
            {
                "id": "a1",
                "type": "Ride",
                "start_date_local": "2026-01-01T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
            },
            {
                "id": "a2",
                "type": "Ride",
                "start_date_local": "2026-01-02T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
            },
        ]
    )

    flag = next(flag for flag in context["flags"] if flag["type"] == "too_many_hard_days_close_together")

    assert flag["subjective_rating"] == {"cycling_session": None}
    assert "intervals_subjective" in context["missing_metrics"]


def test_cycling_co_occurrences_same_week_only() -> None:
    context = build_cycling_context(
        [
            {
                "id": "a1",
                "type": "Ride",
                "start_date_local": "2026-01-01T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
                "feel": 4,
            },
            {
                "id": "a2",
                "type": "Ride",
                "start_date_local": "2026-01-02T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
                "perceived_exertion": 7,
                "feel": 4,
            },
        ],
        wellness=[{"id": "2026-01-02", "ctl": 40, "atl": 55}],
    )

    assert context["co_occurrences"] == [
        {
            "iso_week": "2026-W01",
            "flag_types": ["poor_freshness_before_sprint_work", "too_many_hard_days_close_together"],
            "evidence": {
                "atl": 55.0,
                "ctl": 40.0,
                "cycling_session": {
                    "activity_id": "a2",
                    "date": "2026-01-02",
                    "intensity": None,
                    "name": None,
                    "training_load": 80.0,
                },
                "date": "2026-01-02",
            },
        }
    ]

    different_weeks = build_cycling_context(
        [
            {
                "id": "a1",
                "type": "Ride",
                "start_date_local": "2026-01-01T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
            },
            {
                "id": "a2",
                "type": "Ride",
                "start_date_local": "2026-01-02T10:00:00",
                "moving_time": 1800,
                "icu_training_load": 80,
            },
        ],
        wellness=[{"id": "2026-01-08", "ctl": 40, "atl": 55}],
    )

    assert different_weeks["co_occurrences"] == []
