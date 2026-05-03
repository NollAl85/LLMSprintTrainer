# Analytics Data Audit

Date: 2026-05-03

This audit was rerun after local `.env` credentials were configured for both Hevy and Intervals.icu. Both sources were reachable using read-only probes. No secrets were written to this file.

## Source Reachability

- Hevy: reachable.
- Intervals.icu: reachable.
- Local config present: `HEVY_API_KEY`, `INTERVALS_API_KEY`, and `INTERVALS_ATHLETE_ID`.
- Hevy writes remain gated by `HEVY_WRITE_ENABLED`; this audit did not perform writes.
- Intervals.icu remains read-only in this project.

## Intervals.icu

Probe window: last 30 days ending 2026-05-03.

Observed activity availability:

- 10 activity records returned in the window.
- 5 visible activity records had real activity IDs and were not API placeholder records.
- Some Strava activities can still be hidden by the API and return placeholder records with `_note`.

Observed activity payloads include:

- Stable identifiers and dates: `id`, `start_date`, `start_date_local`, `type`, `name`, `source`, `timezone`.
- Duration and distance: `moving_time`, `elapsed_time`, `icu_recording_time`, `distance`, `icu_distance`.
- Load and intensity: `icu_training_load`, `power_load`, `hr_load`, `pace_load`, `trimp`, `icu_intensity`, `icu_weighted_avg_watts`, `icu_average_watts`, `icu_variability_index`, `icu_joules`.
- Power-model fields: `p_max`, `icu_pm_p_max`, `icu_pm_cp`, `icu_pm_w_prime`, `icu_pm_ftp`, `icu_rolling_p_max`, `icu_rolling_cp`, `icu_rolling_ftp`, `icu_rolling_w_prime`.
- Optional Fitness-view SS fields: `ss_cp`, `ss_p_max`, `ss_w_prime`. These are preserved as raw Intervals.icu values without unit conversion because the API payload does not label their units.
- Summary best-effort fields observed in the probed activity: `Best5Minutepower`, `Best20minutespower`.
- Sprint summary text: `interval_summary`.
- Stream availability metadata: `stream_types`.
- Zone times: `icu_zone_times`, `icu_hr_zone_times`, `gap_zone_times`, `pace_zone_times`.
- Tags field exists as `tags`, but it may be null.

Observed stream endpoint shape:

- `get_activity_streams(..., types=["time", "watts", "cadence"])` returned a list of stream objects.
- Each stream object includes `type` and `data`.
- The sampled activity returned `time`, `watts`, and `cadence` streams with 3476 samples each.
- Power and cadence extraction should support this list-of-streams shape and also tolerate a dict-of-arrays shape for tests/future responses.

Observed intervals endpoint:

- `get_activity_intervals(activity_id)` was reachable.
- The sampled activity returned zero interval objects.
- v1 classification must therefore fall back to streams, summary best efforts, name/tags/interval summary, and load/intensity/duration.

Observed wellness payloads:

- 31 wellness records returned in the 30-day probe window.
- Wellness fields include `ctl`, `atl`, `ctlLoad`, `atlLoad`, `rampRate`, `readiness`, `hrv`, `hrvSDNN`, `restingHR`, `sleepSecs`, `sleepScore`, `sleepQuality`, `fatigue`, `soreness`, `mood`, `motivation`, `stress`, `weight`, `vo2max`, `injury`, and `comments`.

Observed calendar events:

- No events were returned in the probed 30-day window.
- Event schemas remain best-effort from the existing client and docs.

Missing or limited Intervals metrics for analytics v1:

- Short sprint power durations such as 1s, 5s, 10s, 15s, 20s, 30s, 45s, and 60s are not consistently present as activity summary fields.
- Best-power windows should be computed from streams when streams are available.
- If streams are unavailable and no summary field exists for a duration, report the duration in `missing_metrics`.
- Tags and interval objects may be absent even when sprint work occurred.

## Hevy

Probe result: recent workout data was reachable with the local `.env` key.

Observed Hevy availability:

- `list_workouts(page=1, page_size=5)` returned 1 workout.
- `list_routines(page=1, page_size=5)` returned 0 routines.
- `list_exercise_templates(page=1, page_size=5)` returned 5 templates.

Observed workout payloads include:

- Stable identifiers and dates: `id`, `title`, `description`, `start_time`, `end_time`, `created_at`, `updated_at`, `routine_id`.
- Exercises: `exercise_template_id`, `title`, `notes`, `index`, `superset_id`, `sets`.
- Sets: `index`, `type`, `weight_kg`, `reps`, `rpe`, `distance_meters`, `duration_seconds`, `custom_metric`.

Observed exercise template payloads include:

- `id`, `title`, `type`, `equipment`, `primary_muscle_group`, `secondary_muscle_groups`, `is_custom`.

Missing or limited Hevy metrics for analytics v1:

- RPE exists but may be null.
- RIR was not observed.
- e1RM is not directly present and should not be fabricated; strength classification should use set reps/load/RPE heuristics and report uncertainty when RPE/RIR/e1RM are absent.
- Movement patterns must be heuristic substring matches against exercise titles or template titles.
- Unknown exercise titles must go into an `unknown` movement-pattern bucket and add uncertainty, never raise.

## Implementation Implications

- Date bucketing uses `Europe/Berlin`.
- Intervals activities are deduped locally by `id` as a safety layer, while still trusting Intervals primary dedupe.
- All classification outputs must include `heuristic: true` and a `basis` string.
- Missing source fields must populate `missing_metrics`.
- No readiness score, leg-load score, interference flags, HTML report, MCP analytics tools, or planned workout writes belong in analytics v1.
