"""Minimal interface for current and future training data sources."""

from __future__ import annotations

from typing import Protocol


class TrainingDataSource(Protocol):
    """Protocol future sources such as Intervals.icu can implement."""

    def get_recent_activities(self, *, weeks: int = 8) -> list[dict]:
        """Return recent source activities as JSON-serializable dictionaries."""

    def build_context(self, *, weeks: int = 8) -> dict:
        """Build a compact source-specific training context."""
