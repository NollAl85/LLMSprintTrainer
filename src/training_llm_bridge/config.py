"""Environment-based configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from training_llm_bridge.utils.errors import MissingConfigError

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dependency is declared, fallback keeps imports robust.
    load_dotenv = None  # type: ignore[assignment]

DEFAULT_HEVY_API_BASE_URL = "https://api.hevyapp.com"
DEFAULT_INTERVALS_API_BASE_URL = "https://intervals.icu/api/v1"
TRUE_VALUES = {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime settings loaded from environment variables."""

    hevy_api_key: str | None = None
    hevy_api_base_url: str = DEFAULT_HEVY_API_BASE_URL
    hevy_write_enabled: bool = False
    intervals_api_key: str | None = None
    intervals_athlete_id: str | None = None
    intervals_api_base_url: str = DEFAULT_INTERVALS_API_BASE_URL

    @property
    def intervals_configured(self) -> bool:
        """Return true when Intervals.icu read credentials are available."""

        return bool(self.intervals_api_key and self.intervals_athlete_id)

    @classmethod
    def from_env(
        cls,
        *,
        env_file: str | Path | None = ".env",
        require_api_key: bool = False,
    ) -> "Settings":
        """Load settings from process environment and an optional dotenv file."""

        if env_file and load_dotenv is not None:
            load_dotenv(Path(env_file), override=False)

        api_key = os.getenv("HEVY_API_KEY") or None
        if require_api_key and not api_key:
            raise MissingConfigError(
                "HEVY_API_KEY is required for Hevy API reads and real writes. "
                "Create .env from .env.example or set HEVY_API_KEY in your environment."
            )

        base_url = os.getenv("HEVY_API_BASE_URL", DEFAULT_HEVY_API_BASE_URL).rstrip("/")
        write_enabled = _parse_bool(os.getenv("HEVY_WRITE_ENABLED"), default=False)
        intervals_base_url = os.getenv(
            "INTERVALS_API_BASE_URL", DEFAULT_INTERVALS_API_BASE_URL
        ).rstrip("/")

        return cls(
            hevy_api_key=api_key,
            hevy_api_base_url=base_url,
            hevy_write_enabled=write_enabled,
            intervals_api_key=os.getenv("INTERVALS_API_KEY") or None,
            intervals_athlete_id=os.getenv("INTERVALS_ATHLETE_ID") or None,
            intervals_api_base_url=intervals_base_url,
        )


def load_settings(
    *,
    env_file: str | Path | None = ".env",
    require_api_key: bool = False,
) -> Settings:
    """Load project settings."""

    return Settings.from_env(env_file=env_file, require_api_key=require_api_key)


def _parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in TRUE_VALUES
