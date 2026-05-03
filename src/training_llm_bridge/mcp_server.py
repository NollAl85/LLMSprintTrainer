"""Optional MCP server for agent runtimes that support Model Context Protocol."""

from __future__ import annotations

import difflib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from training_llm_bridge.contexts.combined_context import (
    build_combined_training_context as build_combined_training_context_dict,
)
from training_llm_bridge.contexts.cycling_context import build_cycling_context as build_cycling_context_dict
from training_llm_bridge.contexts.lifting_context import build_lifting_context as build_lifting_context_dict
from training_llm_bridge.config import load_settings
from training_llm_bridge.sources.hevy_client import HevyClient
from training_llm_bridge.sources.intervals_client import IntervalsClient
from training_llm_bridge.utils.errors import MissingConfigError

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - optional dependency.
    FastMCP = None  # type: ignore[assignment]


def create_server() -> Any:
    """Create the MCP server."""

    if FastMCP is None:
        raise MissingConfigError("Install MCP support with: uv sync --extra mcp")

    mcp = FastMCP("training-llm-bridge")

    @mcp.tool()
    def hevy_get_recent_workouts(weeks: int = 8) -> list[dict]:
        """Get recent Hevy workouts."""

        with HevyClient() as client:
            return _get_recent_workouts(client, weeks=weeks)

    @mcp.tool()
    def hevy_get_workout(workout_id: str) -> dict:
        """Get one Hevy workout."""

        with HevyClient() as client:
            return client.get_workout(workout_id)

    @mcp.tool()
    def hevy_get_routines() -> dict:
        """Get Hevy routines."""

        with HevyClient() as client:
            return client.list_routines(page=1, page_size=10)

    @mcp.tool()
    def hevy_get_routine(routine_id: str) -> dict:
        """Get one Hevy routine."""

        with HevyClient() as client:
            return client.get_routine(routine_id)

    @mcp.tool()
    def hevy_search_exercises(query: str) -> dict:
        """Search Hevy exercise templates by title."""

        with HevyClient() as client:
            matches = client.search_exercise_templates(query)
        return {"query": query, "matches": matches, "matched_count": len(matches)}

    @mcp.tool()
    def build_lifting_context(weeks: int = 8) -> dict:
        """Build lifting context from recent Hevy workouts."""

        with HevyClient() as client:
            workouts = _get_recent_workouts(client, weeks=weeks)
        return build_lifting_context_dict(workouts)

    @mcp.tool()
    def build_combined_training_context(weeks: int = 8) -> dict:
        """Build combined context with available Hevy and Intervals.icu data."""

        settings = load_settings(require_api_key=False)
        workouts = None
        activities = None
        wellness = None
        events = None
        if settings.hevy_api_key:
            with HevyClient(settings=settings) as client:
                workouts = _get_recent_workouts(client, weeks=weeks)
        if settings.intervals_configured:
            start, end = _date_range_for_weeks(weeks)
            with IntervalsClient(settings=settings) as client:
                activities = client.list_activities(start_date=start, end_date=end)
                wellness = client.list_wellness(start_date=start, end_date=end)
                events = client.list_events(start_date=start, end_date=end)
        return build_combined_training_context_dict(
            workouts,
            activities=activities,
            wellness=wellness,
            events=events,
            weeks=weeks,
        )

    @mcp.tool()
    def intervals_get_recent_activities(weeks: int = 8) -> list[dict]:
        """Get recent Intervals.icu activities."""

        start, end = _date_range_for_weeks(weeks)
        with IntervalsClient() as client:
            return client.list_activities(start_date=start, end_date=end)

    @mcp.tool()
    def intervals_get_activity(activity_id: str) -> dict:
        """Get one Intervals.icu activity."""

        with IntervalsClient() as client:
            return client.get_activity(activity_id)

    @mcp.tool()
    def intervals_get_wellness(weeks: int = 8) -> list[dict]:
        """Get recent Intervals.icu wellness records."""

        start, end = _date_range_for_weeks(weeks)
        with IntervalsClient() as client:
            return client.list_wellness(start_date=start, end_date=end)

    @mcp.tool()
    def build_cycling_context(weeks: int = 8) -> dict:
        """Build cycling context from recent Intervals.icu data."""

        start, end = _date_range_for_weeks(weeks)
        with IntervalsClient() as client:
            activities = client.list_activities(start_date=start, end_date=end)
            wellness = client.list_wellness(start_date=start, end_date=end)
            events = client.list_events(start_date=start, end_date=end)
        return build_cycling_context_dict(activities, wellness=wellness, events=events)

    @mcp.tool()
    def hevy_create_routine(
        name: str,
        notes: str,
        exercises: list[dict],
        dry_run: bool = True,
    ) -> dict:
        """Create a Hevy routine, dry-run by default."""

        payload = {"routine": {"title": name, "notes": notes, "folder_id": None, "exercises": exercises}}
        with HevyClient() as client:
            return client.create_routine(payload, dry_run=dry_run)

    @mcp.tool()
    def hevy_update_routine(routine_id: str, payload: dict, dry_run: bool = True) -> dict:
        """Update a Hevy routine, dry-run by default."""

        with HevyClient() as client:
            before = _try_get_routine(client, routine_id)
            result = client.update_routine(routine_id, payload, dry_run=dry_run)
        return {"before": before, "result": result, "diff": _json_diff(before, result.get("payload", payload))}

    @mcp.tool()
    def hevy_create_workout(payload: dict, dry_run: bool = True) -> dict:
        """Create a Hevy workout, dry-run by default."""

        with HevyClient() as client:
            return client.create_workout(payload, dry_run=dry_run)

    return mcp


def main() -> None:
    """Run the MCP server over stdio."""

    server = create_server()
    server.run()


def _get_recent_workouts(client: HevyClient, *, weeks: int) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=weeks)
    workouts: list[dict] = []
    page = 1
    while True:
        response = client.list_workouts(page=page, page_size=10)
        page_workouts = response.get("workouts", [])
        if not page_workouts:
            break
        stop = False
        for workout in page_workouts:
            start = _parse_datetime(workout.get("start_time"))
            if start is not None and start < cutoff:
                stop = True
                continue
            workouts.append(workout)
        page_count = int(response.get("page_count") or page)
        if stop or page >= page_count:
            break
        page += 1
    return workouts


def _date_range_for_weeks(weeks: int) -> tuple[str, str]:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(weeks=weeks)
    return start.isoformat(), end.isoformat()


def _try_get_routine(client: HevyClient, routine_id: str) -> dict | None:
    if not client.api_key:
        return None
    try:
        return client.get_routine(routine_id)
    except Exception:
        return None


def _json_diff(before: dict | None, after: dict) -> str | None:
    if before is None:
        return None
    before_lines = json.dumps(before, indent=2, sort_keys=True, default=str).splitlines()
    after_lines = json.dumps(after, indent=2, sort_keys=True, default=str).splitlines()
    return "\n".join(
        difflib.unified_diff(before_lines, after_lines, fromfile="before", tofile="after", lineterm="")
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


if __name__ == "__main__":
    main()
