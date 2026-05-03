from __future__ import annotations

import logging

import httpx
import pytest

from training_llm_bridge.config import Settings
from training_llm_bridge.sources.hevy_client import HevyClient
from training_llm_bridge.utils.errors import (
    HevyAuthError,
    HevyNotFoundError,
    HevyRateLimitError,
    HevyValidationError,
    HevyWriteDisabledError,
    MissingConfigError,
)


def make_client(
    handler: httpx.MockTransport,
    *,
    api_key: str | None = "secret-key",
    write_enabled: bool = False,
    max_retries: int = 0,
) -> HevyClient:
    http_client = httpx.Client(transport=handler, base_url="https://api.hevyapp.com")
    settings = Settings(
        hevy_api_key=api_key,
        hevy_api_base_url="https://api.hevyapp.com",
        hevy_write_enabled=write_enabled,
    )
    return HevyClient(settings=settings, client=http_client, max_retries=max_retries, backoff_seconds=0)


def test_missing_api_key_fails_on_read() -> None:
    client = make_client(httpx.MockTransport(lambda _request: httpx.Response(200, json={})), api_key=None)

    with pytest.raises(MissingConfigError, match="HEVY_API_KEY is required"):
        client.list_workouts()


def test_auth_header_is_set_without_logging_key(caplog: pytest.LogCaptureFixture) -> None:
    secret = "super-secret-key"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["api-key"] == secret
        return httpx.Response(200, json={"page": 1, "page_count": 1, "workouts": []})

    client = make_client(httpx.MockTransport(handler), api_key=secret)

    with caplog.at_level(logging.INFO, logger="training_llm_bridge.sources.hevy_client"):
        client.list_workouts()

    assert secret not in caplog.text
    assert client.safe_headers()["api-key"] == "<redacted>"


def test_read_methods_parse_mocked_responses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/workouts":
            assert request.url.params["page"] == "2"
            assert request.url.params["pageSize"] == "5"
            return httpx.Response(
                200,
                json={
                    "page": 2,
                    "page_count": 3,
                    "workouts": [{"id": "w1", "title": "Bench"}],
                },
            )
        if request.url.path == "/v1/workouts/w1":
            return httpx.Response(200, json={"id": "w1", "title": "Bench"})
        raise AssertionError(f"Unexpected path: {request.url.path}")

    client = make_client(httpx.MockTransport(handler))

    assert client.list_workouts(page=2, page_size=5)["workouts"][0]["id"] == "w1"
    assert client.get_workout("w1")["title"] == "Bench"


def test_search_exercise_templates_filters_all_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        page = int(request.url.params["page"])
        if page == 1:
            return httpx.Response(
                200,
                json={
                    "page": 1,
                    "page_count": 2,
                    "exercise_templates": [
                        {"id": "a", "title": "Bench Press (Barbell)"},
                        {"id": "b", "title": "Squat (Barbell)"},
                    ],
                },
            )
        return httpx.Response(
            200,
            json={
                "page": 2,
                "page_count": 2,
                "exercise_templates": [{"id": "c", "title": "Bench Press (Dumbbell)"}],
            },
        )

    client = make_client(httpx.MockTransport(handler))

    matches = client.search_exercise_templates("bench")

    assert [match["id"] for match in matches] == ["a", "c"]


def test_dry_run_write_returns_payload_without_http() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, json={})

    client = make_client(httpx.MockTransport(handler), api_key=None)
    result = client.create_routine({"title": "Dry run", "exercises": []})

    assert calls == 0
    assert result["dry_run"] is True
    assert result["method"] == "POST"
    assert result["path"] == "/v1/routines"
    assert result["payload"] == {"routine": {"title": "Dry run", "exercises": []}}


def test_real_write_requires_write_enabled() -> None:
    client = make_client(httpx.MockTransport(lambda _request: httpx.Response(201, json={})))

    with pytest.raises(HevyWriteDisabledError, match="HEVY_WRITE_ENABLED=true"):
        client.create_routine({"routine": {"title": "Nope", "exercises": []}}, dry_run=False)


def test_real_write_posts_when_enabled() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = request.read().decode()
        return httpx.Response(201, json={"id": "r1", "title": "Routine"})

    client = make_client(httpx.MockTransport(handler), write_enabled=True)

    result = client.create_routine({"routine": {"title": "Routine", "exercises": []}}, dry_run=False)

    assert result["id"] == "r1"
    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/routines"
    assert '"routine"' in str(captured["body"])


@pytest.mark.parametrize(
    ("status", "exception"),
    [
        (401, HevyAuthError),
        (404, HevyNotFoundError),
        (429, HevyRateLimitError),
        (400, HevyValidationError),
    ],
)
def test_status_errors_are_typed(status: int, exception: type[Exception]) -> None:
    client = make_client(
        httpx.MockTransport(lambda _request: httpx.Response(status, json={"error": "bad"}))
    )

    with pytest.raises(exception, match="bad"):
        client.list_workouts()
