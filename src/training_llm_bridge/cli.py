"""Command line interface for training-llm-bridge."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from training_llm_bridge.coach.sprint_constraints import get_sprint_kilo_constraints
from training_llm_bridge.config import load_settings
from training_llm_bridge.contexts.combined_context import build_combined_training_context
from training_llm_bridge.contexts.cycling_context import build_cycling_context
from training_llm_bridge.contexts.lifting_context import build_lifting_context
from training_llm_bridge.sources.hevy_client import HevyClient
from training_llm_bridge.sources.intervals_client import IntervalsClient
from training_llm_bridge.utils.errors import TrainingBridgeError
from training_llm_bridge.utils.logging import configure_logging


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging()

    try:
        result = args.func(args)
    except TrainingBridgeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130

    if result is not None:
        _emit_json(result, out=getattr(args, "out", None))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="training-bridge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    recent = subparsers.add_parser("recent", help="Show recent Hevy workouts.")
    recent.add_argument("--weeks", type=int, default=8)
    recent.add_argument("--out", type=Path)
    recent.set_defaults(func=_cmd_recent)

    context = subparsers.add_parser("context", help="Build LLM context JSON.")
    context_sub = context.add_subparsers(dest="context_type", required=True)
    lifting = context_sub.add_parser("lifting", help="Build lifting context.")
    lifting.add_argument("--weeks", type=int, default=8)
    lifting.add_argument("--out", type=Path)
    lifting.set_defaults(func=_cmd_lifting_context)
    cycling = context_sub.add_parser("cycling", help="Build cycling context.")
    cycling.add_argument("--weeks", type=int, default=8)
    cycling.add_argument("--out", type=Path)
    cycling.set_defaults(func=_cmd_cycling_context)
    combined = context_sub.add_parser("combined", help="Build combined training context.")
    combined.add_argument("--weeks", type=int, default=8)
    combined.add_argument("--out", type=Path)
    combined.set_defaults(func=_cmd_combined_context)

    intervals = subparsers.add_parser("intervals", help="Read Intervals.icu data.")
    intervals_sub = intervals.add_subparsers(dest="intervals_command", required=True)
    intervals_activities = intervals_sub.add_parser("activities", help="List Intervals.icu activities.")
    intervals_activities.add_argument("--start", required=True)
    intervals_activities.add_argument("--end", required=True)
    intervals_activities.add_argument("--out", type=Path)
    intervals_activities.set_defaults(func=_cmd_intervals_activities)
    intervals_wellness = intervals_sub.add_parser("wellness", help="List Intervals.icu wellness.")
    intervals_wellness.add_argument("--start", required=True)
    intervals_wellness.add_argument("--end", required=True)
    intervals_wellness.add_argument("--out", type=Path)
    intervals_wellness.set_defaults(func=_cmd_intervals_wellness)

    routines = subparsers.add_parser("routines", help="List Hevy routines.")
    routines.set_defaults(func=_cmd_routines)

    routine = subparsers.add_parser("routine", help="Get one Hevy routine.")
    routine.add_argument("routine_id")
    routine.set_defaults(func=_cmd_routine)

    exercises = subparsers.add_parser("exercises", help="Search Hevy exercise templates.")
    exercises.add_argument("--query", required=True)
    exercises.set_defaults(func=_cmd_exercises)

    create_routine = subparsers.add_parser("create-routine", help="Create a routine.")
    create_routine.add_argument("routine_json", type=Path)
    create_routine.add_argument("--dry-run", action="store_true", help="Return the payload only.")
    create_routine.add_argument("--write", action="store_true", help="Perform a real write.")
    create_routine.set_defaults(func=_cmd_create_routine)

    update_routine = subparsers.add_parser("update-routine", help="Update a routine.")
    update_routine.add_argument("routine_id")
    update_routine.add_argument("routine_json", type=Path)
    update_routine.add_argument("--dry-run", action="store_true", help="Return the payload only.")
    update_routine.add_argument("--write", action="store_true", help="Perform a real write.")
    update_routine.set_defaults(func=_cmd_update_routine)

    constraints = subparsers.add_parser("constraints", help="Show planning constraints.")
    constraints_sub = constraints.add_subparsers(dest="constraint_type", required=True)
    sprint = constraints_sub.add_parser("sprint-kilo", help="Show sprint/kilo constraints.")
    sprint.set_defaults(func=_cmd_constraints_sprint_kilo)

    return parser


def _cmd_recent(args: argparse.Namespace) -> dict:
    with _hevy_client(require_api_key=True) as client:
        workouts = _get_recent_workouts(client, weeks=args.weeks)
    return {"weeks": args.weeks, "workouts": workouts}


def _cmd_lifting_context(args: argparse.Namespace) -> dict:
    with _hevy_client(require_api_key=True) as client:
        workouts = _get_recent_workouts(client, weeks=args.weeks)
    return build_lifting_context(workouts)


def _cmd_cycling_context(args: argparse.Namespace) -> dict:
    start, end = _date_range_for_weeks(args.weeks)
    with _intervals_client() as client:
        activities = client.list_activities(start_date=start, end_date=end)
        wellness = client.list_wellness(start_date=start, end_date=end)
        events = client.list_events(start_date=start, end_date=end)
    return build_cycling_context(activities, wellness=wellness, events=events)


def _cmd_combined_context(args: argparse.Namespace) -> dict:
    settings = load_settings(require_api_key=False)
    workouts = None
    activities = None
    wellness = None
    events = None

    if settings.hevy_api_key:
        with HevyClient(settings=settings) as client:
            workouts = _get_recent_workouts(client, weeks=args.weeks)

    if settings.intervals_configured:
        start, end = _date_range_for_weeks(args.weeks)
        with IntervalsClient(settings=settings) as client:
            activities = client.list_activities(start_date=start, end_date=end)
            wellness = client.list_wellness(start_date=start, end_date=end)
            events = client.list_events(start_date=start, end_date=end)

    return build_combined_training_context(
        workouts,
        activities=activities,
        wellness=wellness,
        events=events,
        weeks=args.weeks,
    )


def _cmd_intervals_activities(args: argparse.Namespace) -> dict:
    with _intervals_client() as client:
        activities = client.list_activities(start_date=args.start, end_date=args.end)
    return {"start": args.start, "end": args.end, "activities": activities}


def _cmd_intervals_wellness(args: argparse.Namespace) -> dict:
    with _intervals_client() as client:
        wellness = client.list_wellness(start_date=args.start, end_date=args.end)
    return {"start": args.start, "end": args.end, "wellness": wellness}


def _cmd_routines(_args: argparse.Namespace) -> dict:
    with _hevy_client(require_api_key=True) as client:
        return client.list_routines(page=1, page_size=10)


def _cmd_routine(args: argparse.Namespace) -> dict:
    with _hevy_client(require_api_key=True) as client:
        return client.get_routine(args.routine_id)


def _cmd_exercises(args: argparse.Namespace) -> dict:
    with _hevy_client(require_api_key=True) as client:
        matches = client.search_exercise_templates(args.query)
    return {"query": args.query, "matches": matches, "matched_count": len(matches)}


def _cmd_create_routine(args: argparse.Namespace) -> dict:
    payload = _read_json(args.routine_json)
    dry_run = not args.write
    with _hevy_client(require_api_key=not dry_run) as client:
        return client.create_routine(payload, dry_run=dry_run)


def _cmd_update_routine(args: argparse.Namespace) -> dict:
    payload = _read_json(args.routine_json)
    dry_run = not args.write
    with _hevy_client(require_api_key=not dry_run) as client:
        return client.update_routine(args.routine_id, payload, dry_run=dry_run)


def _cmd_constraints_sprint_kilo(_args: argparse.Namespace) -> dict:
    return get_sprint_kilo_constraints()


def _hevy_client(*, require_api_key: bool) -> HevyClient:
    settings = load_settings(require_api_key=require_api_key)
    return HevyClient(settings=settings)


def _intervals_client() -> IntervalsClient:
    settings = load_settings(require_api_key=False)
    return IntervalsClient(settings=settings)


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


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise TrainingBridgeError(f"{path} must contain a JSON object.")
    return value


def _emit_json(value: Any, *, out: Path | None = None) -> None:
    text = json.dumps(value, indent=2, sort_keys=True, default=str)
    if out:
        out.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


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
    raise SystemExit(main())
