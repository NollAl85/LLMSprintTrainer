from __future__ import annotations

import pytest

from training_llm_bridge.config import DEFAULT_HEVY_API_BASE_URL, load_settings
from training_llm_bridge.utils.errors import MissingConfigError


def test_config_loads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HEVY_API_KEY", "secret-key")
    monkeypatch.setenv("HEVY_API_BASE_URL", "https://example.test/")
    monkeypatch.setenv("HEVY_WRITE_ENABLED", "true")

    settings = load_settings(env_file=None)

    assert settings.hevy_api_key == "secret-key"
    assert settings.hevy_api_base_url == "https://example.test"
    assert settings.hevy_write_enabled is True
    assert settings.intervals_configured is False


def test_config_defaults_write_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HEVY_API_KEY", raising=False)
    monkeypatch.delenv("HEVY_API_BASE_URL", raising=False)
    monkeypatch.delenv("HEVY_WRITE_ENABLED", raising=False)

    settings = load_settings(env_file=None)

    assert settings.hevy_api_key is None
    assert settings.hevy_api_base_url == DEFAULT_HEVY_API_BASE_URL
    assert settings.hevy_write_enabled is False
    assert settings.intervals_api_key is None
    assert settings.intervals_athlete_id is None


def test_missing_api_key_error_is_clear(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HEVY_API_KEY", raising=False)

    with pytest.raises(MissingConfigError, match="HEVY_API_KEY is required"):
        load_settings(env_file=None, require_api_key=True)
