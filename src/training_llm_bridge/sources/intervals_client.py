"""Read-only Intervals.icu API client."""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

import httpx

from training_llm_bridge.config import Settings, load_settings
from training_llm_bridge.utils.errors import (
    IntervalsAPIError,
    IntervalsAuthError,
    IntervalsConfigError,
    IntervalsNotFoundError,
    IntervalsRateLimitError,
    IntervalsValidationError,
)
from training_llm_bridge.utils.logging import get_logger, redact_mapping

logger = get_logger(__name__)


class IntervalsClient:
    """Synchronous read-only client for Intervals.icu personal API access."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        api_key: str | None = None,
        athlete_id: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
    ) -> None:
        self.settings = settings or load_settings(require_api_key=False)
        self.api_key = api_key if api_key is not None else self.settings.intervals_api_key
        self.athlete_id = (
            athlete_id if athlete_id is not None else self.settings.intervals_athlete_id
        )
        self.base_url = (base_url or self.settings.intervals_api_base_url).rstrip("/")
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._auth = httpx.BasicAuth("API_KEY", self.api_key) if self.api_key else None
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)
        self._client.headers.update({"Accept": "application/json"})

    def __enter__(self) -> "IntervalsClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client if this instance created it."""

        if self._owns_client:
            self._client.close()

    def safe_headers(self) -> dict[str, Any]:
        """Return HTTP headers with known secret values redacted."""

        return redact_mapping(dict(self._client.headers))

    def get_athlete(self) -> dict:
        """Return the configured athlete profile."""

        return self._request("GET", f"athlete/{self._athlete_id()}/profile")

    def list_activities(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        """Return completed activities for a date range."""

        params = _date_params(start_date, end_date)
        if limit is not None:
            params["limit"] = limit
        response = self._request("GET", f"athlete/{self._athlete_id()}/activities", params=params)
        return _ensure_list(response)

    def get_activity(self, activity_id: str) -> dict:
        """Return one activity by ID."""

        return self._request("GET", f"activity/{activity_id}")

    def get_activity_intervals(self, activity_id: str) -> list[dict]:
        """Return intervals detected or defined for an activity."""

        return _ensure_list(self._request("GET", f"activity/{activity_id}/intervals"))

    def get_activity_streams(
        self,
        activity_id: str,
        stream_types: list[str] | None = None,
    ) -> Any:
        """Return activity streams when available.

        Intervals.icu documents this as ``/activity/{id}/streams{ext}``; this
        client requests JSON via ``.json``.
        """

        params: dict[str, Any] = {}
        if stream_types:
            params["types"] = ",".join(stream_types)
        return self._request("GET", f"activity/{activity_id}/streams.json", params=params)

    def list_wellness(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """Return wellness records for a date range."""

        response = self._request(
            "GET", f"athlete/{self._athlete_id()}/wellness.json", params=_date_params(start_date, end_date)
        )
        return _ensure_list(response)

    def list_events(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[dict]:
        """Return calendar events/planned workouts for a date range."""

        response = self._request(
            "GET", f"athlete/{self._athlete_id()}/events.json", params=_date_params(start_date, end_date)
        )
        return _ensure_list(response)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        expected: Iterable[int] = (200,),
    ) -> Any:
        self._require_config()
        expected_statuses = set(expected)
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(method, path, params=params, auth=self._auth)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self._sleep(attempt)
                    continue
                raise IntervalsAPIError(
                    f"Intervals.icu request failed: {exc.__class__.__name__}"
                ) from exc

            logger.info(
                "intervals_request method=%s path=%s status=%s",
                method,
                path,
                response.status_code,
            )

            if response.status_code in expected_statuses:
                return _response_json(response)
            if _is_transient_status(response.status_code) and attempt < self.max_retries:
                self._sleep(attempt, retry_after=response.headers.get("retry-after"))
                continue
            self._raise_for_status(response)

        raise IntervalsAPIError(f"Intervals.icu request failed: {last_error}")  # pragma: no cover

    def _require_config(self) -> None:
        missing = []
        if not self.api_key:
            missing.append("INTERVALS_API_KEY")
        if not self.athlete_id:
            missing.append("INTERVALS_ATHLETE_ID")
        if missing:
            joined = ", ".join(missing)
            raise IntervalsConfigError(
                f"{joined} required for Intervals.icu reads. Set these in .env or your environment."
            )

    def _athlete_id(self) -> str:
        self._require_config()
        assert self.athlete_id is not None
        return self.athlete_id

    def _sleep(self, attempt: int, retry_after: str | None = None) -> None:
        delay = _retry_after_seconds(retry_after)
        if delay is None:
            delay = min(self.backoff_seconds * (2**attempt), 5.0)
        if delay > 0:
            time.sleep(delay)

    def _raise_for_status(self, response: httpx.Response) -> None:
        body = _response_json(response)
        message = _error_message(body) or f"Intervals.icu API returned HTTP {response.status_code}"

        if response.status_code in {401, 403}:
            raise IntervalsAuthError(message, status_code=response.status_code, response_body=body)
        if response.status_code == 404:
            raise IntervalsNotFoundError(message, status_code=response.status_code, response_body=body)
        if response.status_code == 429:
            raise IntervalsRateLimitError(
                message,
                status_code=response.status_code,
                response_body=body,
                retry_after=response.headers.get("retry-after"),
            )
        if response.status_code in {400, 422}:
            raise IntervalsValidationError(message, status_code=response.status_code, response_body=body)
        raise IntervalsAPIError(message, status_code=response.status_code, response_body=body)


def _date_params(start_date: str | None, end_date: str | None) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if start_date:
        params["oldest"] = start_date
    if end_date:
        params["newest"] = end_date
    return params


def _response_json(response: httpx.Response) -> Any:
    if not response.content:
        return {}
    return response.json()


def _ensure_list(value: Any) -> list[dict]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        data = value.get("data") or value.get("items") or value.get("activities")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


def _error_message(body: Any) -> str | None:
    if not isinstance(body, dict):
        return None
    for key in ("error", "message", "detail"):
        value = body.get(key)
        if value:
            return str(value)
    return None


def _is_transient_status(status_code: int) -> bool:
    return status_code in {408, 429} or 500 <= status_code <= 599


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None
