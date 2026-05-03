"""Small Hevy API client with explicit write safety."""

from __future__ import annotations

import time
from collections.abc import Iterable
from typing import Any

import httpx

from training_llm_bridge.config import Settings, load_settings
from training_llm_bridge.utils.errors import (
    HevyAPIError,
    HevyAuthError,
    HevyNotFoundError,
    HevyRateLimitError,
    HevyValidationError,
    HevyWriteDisabledError,
    MissingConfigError,
)
from training_llm_bridge.utils.logging import get_logger, redact_mapping

logger = get_logger(__name__)


class HevyClient:
    """Synchronous client for the official Hevy public API.

    The official public API uses an ``api-key`` header and ``pageSize`` query
    parameter. Mutating methods always dry-run by default.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        write_enabled: bool | None = None,
        client: httpx.Client | None = None,
        timeout: float = 20.0,
        max_retries: int = 2,
        backoff_seconds: float = 0.25,
    ) -> None:
        self.settings = settings or load_settings(require_api_key=False)
        self.api_key = api_key if api_key is not None else self.settings.hevy_api_key
        self.base_url = (base_url or self.settings.hevy_api_base_url).rstrip("/")
        self.write_enabled = (
            write_enabled if write_enabled is not None else self.settings.hevy_write_enabled
        )
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=self.base_url, timeout=timeout)

        self._client.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        if self.api_key:
            self._client.headers.update({"api-key": self.api_key})

    def __enter__(self) -> "HevyClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying HTTP client if this instance created it."""

        if self._owns_client:
            self._client.close()

    def safe_headers(self) -> dict[str, Any]:
        """Return HTTP headers with secret values redacted for diagnostics."""

        return redact_mapping(dict(self._client.headers))

    def list_workouts(self, page: int = 1, page_size: int = 10) -> dict:
        """Return a paginated list of workouts."""

        return self._request("GET", "/v1/workouts", params=_page_params(page, page_size))

    def get_workout(self, workout_id: str) -> dict:
        """Return one workout by ID."""

        return self._request("GET", f"/v1/workouts/{workout_id}")

    def list_routines(self, page: int = 1, page_size: int = 10) -> dict:
        """Return a paginated list of routines."""

        return self._request("GET", "/v1/routines", params=_page_params(page, page_size))

    def get_routine(self, routine_id: str) -> dict:
        """Return one routine by ID."""

        return self._request("GET", f"/v1/routines/{routine_id}")

    def list_exercise_templates(self, page: int = 1, page_size: int = 100) -> dict:
        """Return a paginated list of exercise templates."""

        return self._request("GET", "/v1/exercise_templates", params=_page_params(page, page_size))

    def search_exercise_templates(self, query: str) -> list[dict]:
        """Search exercise templates client-side by title.

        The public API exposes paginated listing but not a dedicated search endpoint.
        """

        needle = query.strip().lower()
        matches: list[dict] = []
        page = 1
        while True:
            response = self.list_exercise_templates(page=page, page_size=100)
            templates = response.get("exercise_templates", [])
            for template in templates:
                title = str(template.get("title", ""))
                if not needle or needle in title.lower():
                    matches.append(template)
            page_count = int(response.get("page_count") or page)
            if page >= page_count:
                break
            page += 1
        return matches

    def create_routine(self, routine_payload: dict, dry_run: bool = True) -> dict:
        """Create a routine, or return the payload when dry-running."""

        payload = _ensure_root(routine_payload, "routine")
        return self._mutating_request("POST", "/v1/routines", payload, dry_run=dry_run, expected=(201,))

    def update_routine(self, routine_id: str, routine_payload: dict, dry_run: bool = True) -> dict:
        """Update a routine, or return the payload when dry-running."""

        payload = _ensure_root(routine_payload, "routine")
        return self._mutating_request(
            "PUT", f"/v1/routines/{routine_id}", payload, dry_run=dry_run, expected=(200,)
        )

    def create_workout(self, workout_payload: dict, dry_run: bool = True) -> dict:
        """Create a workout, or return the payload when dry-running."""

        payload = _ensure_root(workout_payload, "workout")
        return self._mutating_request("POST", "/v1/workouts", payload, dry_run=dry_run, expected=(201,))

    def update_workout(self, workout_id: str, workout_payload: dict, dry_run: bool = True) -> dict:
        """Update a workout, or return the payload when dry-running."""

        payload = _ensure_root(workout_payload, "workout")
        return self._mutating_request(
            "PUT", f"/v1/workouts/{workout_id}", payload, dry_run=dry_run, expected=(200,)
        )

    def _mutating_request(
        self,
        method: str,
        path: str,
        payload: dict,
        *,
        dry_run: bool,
        expected: Iterable[int],
    ) -> dict:
        if dry_run:
            return {"dry_run": True, "method": method, "path": path, "payload": payload}

        if not self.write_enabled:
            raise HevyWriteDisabledError(
                "Hevy write blocked: set HEVY_WRITE_ENABLED=true and pass dry_run=False "
                "to allow a real mutating request."
            )

        self._require_api_key()
        return self._request(method, path, json=payload, expected=expected)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        expected: Iterable[int] = (200,),
    ) -> dict:
        self._require_api_key()

        last_error: Exception | None = None
        expected_statuses = set(expected)

        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.request(method, path, params=params, json=json)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self._sleep(attempt)
                    continue
                raise HevyAPIError(f"Hevy request failed: {exc.__class__.__name__}") from exc

            logger.info("hevy_request method=%s path=%s status=%s", method, path, response.status_code)

            if response.status_code in expected_statuses:
                return _response_json(response)

            if _is_transient_status(response.status_code) and attempt < self.max_retries:
                self._sleep(attempt, retry_after=response.headers.get("retry-after"))
                continue

            self._raise_for_status(response)

        raise HevyAPIError(f"Hevy request failed: {last_error}")  # pragma: no cover

    def _sleep(self, attempt: int, retry_after: str | None = None) -> None:
        delay = _retry_after_seconds(retry_after)
        if delay is None:
            delay = min(self.backoff_seconds * (2**attempt), 5.0)
        if delay > 0:
            time.sleep(delay)

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise MissingConfigError(
                "HEVY_API_KEY is required for Hevy API reads and real writes. "
                "Create .env from .env.example or set HEVY_API_KEY in your environment."
            )

    def _raise_for_status(self, response: httpx.Response) -> None:
        body = _response_json(response)
        message = _error_message(body) or f"Hevy API returned HTTP {response.status_code}"

        if response.status_code in {401, 403}:
            raise HevyAuthError(message, status_code=response.status_code, response_body=body)
        if response.status_code == 404:
            raise HevyNotFoundError(message, status_code=response.status_code, response_body=body)
        if response.status_code == 429:
            raise HevyRateLimitError(
                message,
                status_code=response.status_code,
                response_body=body,
                retry_after=response.headers.get("retry-after"),
            )
        if response.status_code in {400, 422}:
            raise HevyValidationError(message, status_code=response.status_code, response_body=body)
        raise HevyAPIError(message, status_code=response.status_code, response_body=body)


def _page_params(page: int, page_size: int) -> dict[str, int]:
    return {"page": page, "pageSize": page_size}


def _ensure_root(payload: dict, root: str) -> dict:
    if root in payload:
        return payload
    return {root: payload}


def _response_json(response: httpx.Response) -> dict:
    if not response.content:
        return {}
    parsed = response.json()
    if isinstance(parsed, dict):
        return parsed
    return {"data": parsed}


def _error_message(body: dict) -> str | None:
    for key in ("error", "message", "detail"):
        value = body.get(key)
        if value:
            return str(value)
    return None


def _is_transient_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        return None
