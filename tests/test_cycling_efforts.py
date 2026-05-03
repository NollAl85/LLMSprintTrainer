from __future__ import annotations

from training_llm_bridge.analytics.cycling_efforts import (
    CyclingClassificationConfig,
    build_power_baselines,
    classify_cycling_activity,
    compute_best_power_windows,
    detect_near_max_efforts,
    extract_power_series,
)


def test_best_power_windows_over_synthetic_series() -> None:
    series = [(idx, watts) for idx, watts in enumerate([100, 200, 300, 400, 500])]

    assert compute_best_power_windows(series, [1, 3, 5]) == {1: 500, 3: 400, 5: 300}


def test_near_max_detection() -> None:
    series = [(idx, 100) for idx in range(10)] + [(idx, 200) for idx in range(10, 20)]
    baselines = {"max_power_watts": {"5": 200}}

    counts = detect_near_max_efforts(series, baselines, [5], threshold=0.95)

    assert counts[5] == 6


def test_pmax_sprint_classification_from_streams() -> None:
    activity = {
        "id": "a1",
        "name": "Sprint day",
        "type": "Ride",
        "start_date_local": "2026-01-01T10:00:00",
        "moving_time": 20,
        "streams": {"time": list(range(20)), "watts": [100] * 10 + [1000] * 10},
    }
    baselines = {"max_power_watts": {"5": 1000, "10": 1000}}

    result = classify_cycling_activity(activity, baselines=baselines)

    assert result["primary_tag"] == "pmax_sprint"
    assert result["basis"] == "from streams + baselines"
    assert result["heuristic"] is True


def test_frc_anaerobic_classification_from_long_near_max() -> None:
    activity = {
        "id": "a2",
        "name": "Anaerobic work",
        "type": "Ride",
        "start_date_local": "2026-01-02T10:00:00",
        "moving_time": 180,
        "streams": {"time": list(range(180)), "watts": [500] * 180},
    }
    baselines = {"max_power_watts": {"120": 500, "180": 500}}

    result = classify_cycling_activity(activity, baselines=baselines)

    assert result["primary_tag"] == "frc_anaerobic"


def test_recovery_fallback_classification() -> None:
    activity = {
        "id": "a3",
        "name": "Short aerobic",
        "type": "Ride",
        "start_date_local": "2026-01-03T10:00:00",
        "moving_time": 1800,
        "icu_training_load": 10,
        "icu_intensity": 45,
    }

    result = classify_cycling_activity(activity)

    assert result["primary_tag"] == "recovery_easy"
    assert result["basis"] == "fallback from load + intensity + duration"
    assert "power_stream" in result["missing_metrics"]


def test_missing_stream_graceful_path_and_baselines() -> None:
    activity = {
        "id": "a4",
        "type": "Ride",
        "start_date_local": "2026-01-04T10:00:00",
        "Best5Minutepower": 250,
    }

    assert extract_power_series(activity) is None
    baselines = build_power_baselines([activity])

    assert baselines["max_power_watts"]["300"] == 250
    assert "baseline_1s" in baselines["missing_metrics"]


def test_ss_power_model_fields_are_preserved() -> None:
    activity = {
        "id": "a6",
        "type": "Ride",
        "start_date_local": "2026-01-06T10:00:00",
        "moving_time": 1800,
        "ss_cp": 50.51385,
        "ss_p_max": 11.039366,
        "ss_w_prime": 3.0405822,
    }

    result = classify_cycling_activity(activity)

    assert result["ss_power_model"] == {
        "ss_cp": 50.51385,
        "ss_p_max": 11.039366,
        "ss_w_prime": 3.0405822,
    }
    assert "ss_cp" not in result["missing_metrics"]


def test_config_can_be_passed_explicitly() -> None:
    activity = {
        "id": "a5",
        "type": "Ride",
        "start_date_local": "2026-01-05T10:00:00",
        "moving_time": 3600,
        "icu_training_load": 80,
        "icu_intensity": 70,
    }
    config = CyclingClassificationConfig(mixed_hard_min_load=100)

    result = classify_cycling_activity(activity, config=config)

    assert result["primary_tag"] == "z2_aerobic"
