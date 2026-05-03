"""Prompt snippets for LLM review and routine generation."""

from __future__ import annotations

import json


def weekly_review_prompt(context: dict) -> str:
    """Prompt an LLM to review recent training without writing to Hevy."""

    return (
        "Review the following lifting context for cycling sprint/kilo preparation. "
        "Identify stalled lifts, volume imbalances, lower-body fatigue risks, and anything "
        "likely to interfere with 15s/30s/60s sprint power. Do not write to Hevy.\n\n"
        f"Context:\n{_json(context)}"
    )


def routine_generation_prompt(context: dict, goal: str) -> str:
    """Prompt an LLM to draft a Hevy routine payload using dry-run first."""

    return (
        "Create a Hevy routine payload for the goal below. Prioritize sprint freshness over "
        "hypertrophy unless explicitly requested. Use the official Hevy routine shape with "
        "a top-level 'routine' object. Return a dry-run payload first.\n\n"
        f"Goal: {goal}\n\nContext:\n{_json(context)}"
    )


def routine_safety_review_prompt(proposed_routine: dict, context: dict) -> str:
    """Prompt an LLM to review a proposed routine for sprint/kilo interference."""

    return (
        "Compare this proposed Hevy routine against the recent training context. Reduce or "
        "flag leg volume that is likely to interfere with cycling sprint/kilo power. Do not "
        "write to Hevy unless the user explicitly asks for a real write.\n\n"
        f"Proposed routine:\n{_json(proposed_routine)}\n\nContext:\n{_json(context)}"
    )


def weekly_combined_review_prompt(context: dict) -> str:
    """Prompt an LLM to review Hevy + Intervals data without writing plans."""

    return (
        "Review the combined Hevy lifting and Intervals.icu cycling context for cycling "
        "sprint/kilo performance. Treat 15s/30s/60s power quality as the primary outcome. "
        "Distinguish productive overload from accumulating fatigue, and identify lifting "
        "or cycling patterns that may compromise sprint freshness. Do not write planned "
        "workouts or modify any external system.\n\n"
        f"Context:\n{_json(context)}"
    )


def sprint_power_trend_review_prompt(context: dict) -> str:
    """Prompt an LLM to evaluate sprint power trends."""

    return (
        "Analyze sprint-relevant power trends in this context, especially 5s, 10s, 15s, "
        "30s, and 60s efforts. Explain whether changes look like productive overload, "
        "normal variability, or fatigue accumulation. Use available Intervals.icu metrics "
        "only; call out missing metrics clearly. Do not write planned workouts.\n\n"
        f"Context:\n{_json(context)}"
    )


def lifting_interference_review_prompt(context: dict) -> str:
    """Prompt an LLM to review lifting interference with sprint work."""

    return (
        "Review whether Hevy lower-body lifting is likely interfering with cycling "
        "sprint/kilo work. Pay special attention to hard leg lifting within 24-48h of "
        "key sprint sessions, rising lower-body volume, and weeks with multiple sprint "
        "sessions. Preserve sprint quality over hypertrophy unless explicitly requested. "
        "Do not write planned workouts.\n\n"
        f"Context:\n{_json(context)}"
    )


def next_week_constraints_prompt(context: dict) -> str:
    """Prompt an LLM to extract constraints for next week's planning."""

    return (
        "Extract next-week training constraints from this combined context. Prioritize "
        "cycling sprint/kilo performance, avoid destroying 15s/30s/60s power with "
        "excessive lower-body fatigue, and separate strength maintenance from leg "
        "hypertrophy work. Produce constraints only; do not create or write planned "
        "workouts yet.\n\n"
        f"Context:\n{_json(context)}"
    )


def _json(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, default=str)
