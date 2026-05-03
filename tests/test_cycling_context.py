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
        "power_5s": 900,
        "power_15s": 780,
        "power_30s": 650,
        "power_60s": 520,
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
    assert context["wellness_summary"]["latest"]["ctl"] == 60


def test_missing_sprint_power_metrics_are_handled_gracefully() -> None:
    context = build_cycling_context(
        [{"id": "a3", "type": "Ride", "start_date_local": "2026-01-01", "moving_time": 1800}]
    )

    assert context["sprint_power"]["max_5s_power"] is None
    assert "max_5s_power" in context["missing_metrics"]
