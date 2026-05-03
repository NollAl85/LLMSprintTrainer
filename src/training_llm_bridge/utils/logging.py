"""Logging helpers that avoid exposing secrets."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

SENSITIVE_KEYS = {
    "api-key",
    "authorization",
    "hevy_api_key",
    "HEVY_API_KEY",
    "token",
    "access_token",
    "intervals_api_key",
    "INTERVALS_API_KEY",
}


def configure_logging(level: int = logging.INFO) -> None:
    """Configure a small default logger for CLI use."""

    logging.basicConfig(level=level, format="%(levelname)s %(name)s: %(message)s")


def get_logger(name: str) -> logging.Logger:
    """Return a module logger."""

    return logging.getLogger(name)


def redact_mapping(values: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy of a mapping with known secret keys redacted."""

    redacted: dict[str, Any] = {}
    for key, value in values.items():
        if key in SENSITIVE_KEYS or key.lower() in SENSITIVE_KEYS:
            redacted[key] = "<redacted>"
        else:
            redacted[key] = value
    return redacted
