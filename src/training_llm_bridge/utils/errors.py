"""Custom exceptions used by the training bridge."""

from __future__ import annotations

from typing import Any


class TrainingBridgeError(Exception):
    """Base exception for this project."""


class ConfigError(TrainingBridgeError):
    """Raised when configuration is invalid."""


class MissingConfigError(ConfigError):
    """Raised when required configuration is missing."""


class HevyAPIError(TrainingBridgeError):
    """Raised for Hevy API errors that do not have a more specific type."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class HevyAuthError(HevyAPIError):
    """Raised for authentication or permission errors."""


class HevyRateLimitError(HevyAPIError):
    """Raised when Hevy rate-limits a request."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any | None = None,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_body=response_body)
        self.retry_after = retry_after


class HevyValidationError(HevyAPIError):
    """Raised when Hevy rejects a request body or query parameter."""


class HevyNotFoundError(HevyAPIError):
    """Raised when a Hevy resource does not exist or is not available."""


class HevyWriteDisabledError(TrainingBridgeError):
    """Raised when a real mutating request is blocked by local write safety."""


class IntervalsConfigError(ConfigError):
    """Raised when Intervals.icu configuration is missing or invalid."""


class IntervalsAPIError(TrainingBridgeError):
    """Raised for Intervals.icu API errors that do not have a more specific type."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class IntervalsAuthError(IntervalsAPIError):
    """Raised for Intervals.icu authentication or permission errors."""


class IntervalsRateLimitError(IntervalsAPIError):
    """Raised when Intervals.icu rate-limits a request."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any | None = None,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(message, status_code=status_code, response_body=response_body)
        self.retry_after = retry_after


class IntervalsValidationError(IntervalsAPIError):
    """Raised when Intervals.icu rejects request parameters."""


class IntervalsNotFoundError(IntervalsAPIError):
    """Raised when an Intervals.icu resource is not found."""
