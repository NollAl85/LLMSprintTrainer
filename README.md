# training-llm-bridge

A small local Python bridge that lets an LLM coding agent or a normal terminal read Hevy lifting history, read Intervals.icu cycling/wellness data, and safely draft or write Hevy routines/workouts through the official Hevy API.

This is not a production app, web app, or hosted service. It does not depend on hosted HevyGPT. HevyGPT can be useful as a reference for routine representation, but this project calls the official Hevy API directly.

## What Works In V1.1

- Read Hevy workouts, routines, and exercise templates.
- Read Intervals.icu activities, wellness records, planned calendar events, activity details, intervals, and streams.
- Build compact lifting context for LLM review.
- Build compact cycling context for sprint/kilo review.
- Build a combined training context with available Hevy lifting data, Intervals cycling/wellness data, sprint/kilo constraints, missing-source reporting, and cross-training flags.
- Dry-run or write Hevy routines and workouts, with writes blocked by default.
- Keep Intervals.icu read-only.
- Use everything from the CLI.
- Optionally expose the same functions through an MCP server.

## What Is Not Implemented Yet

- Full production scheduling/planning app.
- Deletes.
- Intervals.icu writes.
- Planned workout creation.
- Hosted or remote server deployment.

Hevy and Intervals.icu are separate sources because they have different data models, auth, cadence, and planning roles. Hevy is the lifting source. Intervals.icu is the cycling, wellness, and calendar context source.

## Hevy API Key

Hevy API access currently requires Hevy Pro. Generate the key in the Hevy web app at:

https://hevy.com/settings?developer

The official public API docs are at:

https://api.hevyapp.com/docs/

The public API uses an `api-key` header. Do not put the key in prompts, logs, screenshots, or committed files.

## Intervals.icu API Key

Generate a personal API key near the bottom of Intervals.icu settings:

https://intervals.icu/settings

The API docs and cookbook are at:

https://www.intervals.icu/features/open-api/

https://forum.intervals.icu/t/intervals-icu-api-integration-cookbook/80090

For personal API key access, Intervals.icu uses Basic Auth with username `API_KEY` and password equal to your API key. Your athlete ID is visible in Intervals.icu URLs and profile/API responses. Many personal API examples also allow athlete ID `0`, but this project expects `INTERVALS_ATHLETE_ID` explicitly.

## Configuration

Create `.env`:

```sh
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Fill it in:

```dotenv
HEVY_API_KEY=your_key_here
HEVY_API_BASE_URL=https://api.hevyapp.com
HEVY_WRITE_ENABLED=false

INTERVALS_API_KEY=your_intervals_key_here
INTERVALS_ATHLETE_ID=i123456
INTERVALS_API_BASE_URL=https://intervals.icu/api/v1
```

Reads work when `HEVY_API_KEY` is set. Real writes require both `HEVY_WRITE_ENABLED=true` and `dry_run=False`.

Intervals.icu is optional. If Intervals credentials are missing, Hevy-only combined context still works. If Hevy is missing but Intervals is configured, cycling-only combined context works.

## Install

With uv:

```sh
uv sync --extra dev
```

With uv plus MCP support:

```sh
uv sync --extra dev --extra mcp
```

Without uv:

```sh
python -m venv .venv
python -m pip install -e ".[dev]"
```

Without uv plus MCP support:

```sh
python -m pip install -e ".[dev,mcp]"
```

## Tests

```sh
uv run pytest
```

or:

```sh
python -m pytest
```

## CLI Examples

```sh
uv run training-bridge recent --weeks 8
uv run training-bridge context lifting --weeks 8 --out lifting_context.json
uv run training-bridge context combined --weeks 8 --out training_context.json
uv run training-bridge routines
uv run training-bridge routine ROUTINE_ID
uv run training-bridge exercises --query "bench press"
uv run training-bridge intervals activities --start 2026-01-01 --end 2026-01-31 --out activities.json
uv run training-bridge intervals wellness --start 2026-01-01 --end 2026-01-31 --out wellness.json
uv run training-bridge context cycling --weeks 8 --out cycling_context.json
uv run training-bridge create-routine routine.json --dry-run
uv run training-bridge create-routine routine.json --write
uv run training-bridge update-routine ROUTINE_ID routine.json --dry-run
uv run training-bridge update-routine ROUTINE_ID routine.json --write
uv run training-bridge constraints sprint-kilo
```

Equivalent module usage after install:

```sh
python -m training_llm_bridge.cli recent --weeks 8
python -m training_llm_bridge.cli context combined --weeks 8 --out training_context.json
python -m training_llm_bridge.cli context cycling --weeks 8 --out cycling_context.json
python -m training_llm_bridge.cli create-routine routine.json --dry-run
```

## MCP Server

Install MCP support, then run:

```sh
uv run training-bridge-mcp
```

or:

```sh
python -m training_llm_bridge.mcp_server
```

Example Claude Code / Claude Desktop MCP config:

```json
{
  "mcpServers": {
    "training-llm-bridge": {
      "command": "uv",
      "args": [
        "--directory",
        "/absolute/path/to/training-llm-bridge",
        "run",
        "training-bridge-mcp"
      ],
      "env": {
        "HEVY_API_KEY": "your_hevy_api_key",
        "HEVY_API_BASE_URL": "https://api.hevyapp.com",
        "HEVY_WRITE_ENABLED": "false",
        "INTERVALS_API_KEY": "your_intervals_api_key",
        "INTERVALS_ATHLETE_ID": "your_athlete_id",
        "INTERVALS_API_BASE_URL": "https://intervals.icu/api/v1"
      }
    }
  }
}
```

The same example is in `.mcp.example.json`.

## Notes For Agents

Codex, Claude Code, Google Antigravity, Cursor, and normal terminal users should use the CLI first. MCP is optional and should not be required for any core workflow. Keep Hevy write operations dry-run-first, keep Intervals read-only, and never expose API keys.

## Example LLM Prompts

Review my last 8 weeks of lifting. Identify stalled lifts, volume imbalances, and anything that might interfere with cycling sprint/kilo training. Do not write anything yet.

Build a combined training context from Hevy and Intervals.icu. Identify lower-body lifting that may be compromising sprint power, but do not write planned workouts yet.

Create a 3-day lifting routine optimized around cycling sprint training. Use dry-run first. Prioritize sprint freshness over hypertrophy.

Compare this proposed routine against my last 6 weeks and reduce leg volume if it is likely to interfere with 15s/30s/60s sprint power.

Create a low-volume heavy lower-body routine that maintains strength but minimizes DOMS and fatigue before sprint sessions.

Review my 15s/30s/60s power trends and compare them with lower-body lifting volume. Distinguish productive overload from accumulating fatigue.

## Analytics (v1)

Analytics v1 is data-first. It builds a daily exposure calendar from inspected Hevy and Intervals.icu inputs, but it does not invent a combined readiness score, leg-load score, or interference flag. The goal is to make raw exposures inspectable before adding higher-level interpretation.

All classifications are heuristic and labelled. Each classified cycling activity and strength workout includes `heuristic: true`, a `basis` string, evidence fields, and `missing_metrics` when required data is unavailable. Thresholds and movement mappings are editable rather than hidden in call sites.

Intervals.icu SS Fitness-view metrics are preserved when present as raw activity fields: `ss_cp`, `ss_p_max`, and `ss_w_prime`. The bridge does not convert or rename their units because the API response does not label them.

Strength analytics include a `leg_stress` summary split into `quads` and `posterior_chain`. This is based on movement-pattern set counts and tracked load, not a validated fatigue score. Reverse Nordic curls are treated as quad/knee-dominant work.

Run:

```sh
uv run training-bridge analytics calendar --weeks 12 \
  --out-json exposure_calendar.json \
  --out-csv exposure_calendar.csv
```

If only one source is configured, the command builds a one-sided calendar and prints a stderr banner naming the missing source.

The JSON output includes a `weekly_summary` block with cycling totals, strength totals, and raw weekly sums for `ss_cp`, `ss_p_max`, and `ss_w_prime`.

Example calendar rows:

```json
[
  {
    "date": "2026-01-01",
    "cycling": {
      "activity_count": 1,
      "primary_tags": ["pmax_sprint"],
      "ss_power_model": {
        "latest": { "ss_cp": 50.51, "ss_p_max": 11.04, "ss_w_prime": 3.04 }
      }
    },
    "strength": { "workout_count": 1, "primary_session_tags": ["max_strength"] },
    "missing_metrics": ["rpe"]
  },
  {
    "date": "2026-01-02",
    "cycling": { "activity_count": 0 },
    "strength": { "workout_count": 0 },
    "wellness": { "ctl": 50, "atl": 47 }
  },
  {
    "date": "2026-01-03",
    "cycling": { "activity_count": 1, "primary_tags": ["recovery_easy"] },
    "strength": { "workout_count": 0 }
  }
]
```

Override editable analytics config by creating files with the same names in another directory and setting:

```sh
TRAINING_BRIDGE_ANALYTICS_CONFIG_DIR=/path/to/analytics-config
```

Files that can be shadowed:

- `movement_patterns.yaml`
- `leg_stress_patterns.yaml`
- `cycling_classification.yaml`
- `strength_classification.yaml`

Known v1 limitations:

- No standalone sprint-quality panel.
- No energy-system exposure panel.
- No interference flags.
- No HTML report.
- No MCP analytics tools.
- No combined analytics context.
- Rows are emitted only for dates present in cycling, strength, or wellness inputs; empty-day gap filling is intentionally minimal.
- Power baselines need roughly 90 days of useful power data to become meaningful.

Roadmap pointer: v2 should add sprint-quality panels, energy-system exposure panels, transparent interference flags, and richer reports without hiding the raw daily exposure table.

## Roadmap

- v1.2: weekly combined review workflow.
- v1.3: dry-run planned workouts.
- v1.4: optional calendar writes, still gated by explicit write safety.

## Example Dry-Run Routine Payload

```json
{
  "routine": {
    "title": "Low-volume lower body strength maintenance",
    "folder_id": null,
    "notes": "Sprint freshness first. Keep reps crisp and stop well before grinding.",
    "exercises": [
      {
        "exercise_template_id": "D04AC939",
        "superset_id": null,
        "rest_seconds": 180,
        "notes": "Heavy but fast concentric. No failure reps.",
        "sets": [
          {
            "type": "normal",
            "weight_kg": null,
            "reps": 3,
            "rep_range": null
          },
          {
            "type": "normal",
            "weight_kg": null,
            "reps": 3,
            "rep_range": null
          }
        ]
      },
      {
        "exercise_template_id": "2B4B7310",
        "superset_id": null,
        "rest_seconds": 180,
        "notes": "Low volume posterior-chain maintenance.",
        "sets": [
          {
            "type": "normal",
            "weight_kg": null,
            "reps": 5,
            "rep_range": null
          }
        ]
      }
    ]
  }
}
```

Dry-run command:

```sh
uv run training-bridge create-routine routine.json --dry-run
```

Real write command, only after review:

```sh
uv run training-bridge create-routine routine.json --write
```
