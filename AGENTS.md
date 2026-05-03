# AGENTS.md

## Purpose

`training-llm-bridge` is a small local Python project that lets coding agents and humans read Hevy lifting history, read Intervals.icu cycling/wellness context, and safely draft or write Hevy routines/workouts through the official Hevy API.

v1.1 includes Intervals.icu read-only support. Intervals writes, planned workout creation, and calendar writes remain future scope.

## Safety Model

- Reads require `HEVY_API_KEY`.
- Real writes require both `HEVY_WRITE_ENABLED=true` and `dry_run=False`.
- Mutating operations default to `dry_run=True`.
- Dry-runs must return the payload that would be sent to Hevy and must not call POST or PUT.
- Do not implement deletes in v1.1.
- Do not implement Intervals.icu writes in v1.1.
- Never print, log, or commit API keys.
- Never commit `.env`.
- If a real write is blocked, return a clear error explaining the missing safety condition.

## Setup

With uv:

```sh
uv sync --extra dev
```

Without uv:

```sh
python -m venv .venv
python -m pip install -e ".[dev]"
```

Create local configuration:

```sh
cp .env.example .env
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
```

## Test Commands

```sh
uv run pytest
```

or:

```sh
python -m pytest
```

## Style Expectations

- Keep abstractions small and explicit.
- Prefer stable public interfaces over clever internal design.
- Use `pathlib` for filesystem paths.
- Keep CLI functionality complete without MCP.
- Use type hints and docstrings for public functions/methods.
- Keep output JSON-serializable.
- Avoid platform-specific scripts and shell assumptions.

## Hevy API Notes

- Use the official Hevy API directly.
- The public API uses the `api-key` header.
- Pagination uses `page` and `pageSize`.
- Routine and workout create/update payloads are wrapped under top-level `routine` or `workout`.
- Hosted HevyGPT is not a dependency. Its public config can be used only as a reference for how routines/plans are represented.

## Intervals.icu API Notes

- Intervals.icu is read-only in v1.1.
- Personal API key auth uses Basic Auth with username `API_KEY` and password `INTERVALS_API_KEY`.
- Use `INTERVALS_ATHLETE_ID` in endpoint paths.
- Activity and wellness range parameters are `oldest` and `newest`.
- Do not add planned workout writes yet.

## Agent Compatibility

This repo should remain usable from Codex, Claude Code, Google Antigravity, Cursor, and a normal terminal:

- Keep the CLI as the primary interface.
- Keep MCP optional.
- Do not assume a specific IDE or agent runtime.
- Do not add hosted services or a web app for v1.1.

## Future Scope

Roadmap:

- v1.2: weekly combined review workflow.
- v1.3: dry-run planned workouts.
- v1.4: optional calendar writes behind explicit safety gates.
