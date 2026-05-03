"""Lightweight context models."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExerciseSet(BaseModel):
    model_config = ConfigDict(extra="allow")

    index: int | None = None
    type: str | None = None
    weight_kg: float | None = None
    reps: float | None = None
    distance_meters: float | None = None
    duration_seconds: float | None = None
    rpe: float | None = None


class ExercisePerformance(BaseModel):
    model_config = ConfigDict(extra="allow")

    exercise_template_id: str | None = None
    title: str
    sets: int = 0
    total_volume_kg: float = 0
    top_set: dict[str, Any] | None = None
    estimated_1rm_kg: float | None = None


class WorkoutSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    title: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    total_sets: int = 0
    total_volume_kg: float = 0
    exercises: list[str] = []


class RoutineSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    title: str | None = None
    folder_id: int | float | None = None
    exercise_count: int = 0


class LiftingContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    number_of_workouts: int
    date_range: dict[str, str | None]
    workouts_per_week: float | None = None
    total_sets: int = 0
    total_volume_kg: float = 0
    exercises_performed: list[str] = []
    metadata: dict[str, Any] = {}


class CyclingContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    integrated: bool = True
    source: str = "intervals_icu"
    date_range: dict[str, str | None] = {}
    number_of_cycling_activities: int = 0
    missing_metrics: list[str] = []
    co_occurrences: list[dict[str, Any]] = Field(default_factory=list)


class CombinedTrainingContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    lifting: dict[str, Any] | None = None
    cycling: dict[str, Any] | None = None
    wellness: dict[str, Any] | None = None
    constraints: dict[str, Any]
    cross_training_flags: list[dict[str, Any]] = []
    co_occurrences: list[dict[str, Any]] = Field(default_factory=list)
    recommendations_ready: bool = True
    missing_sources: list[str] = []
    metadata: dict[str, Any] = {}
