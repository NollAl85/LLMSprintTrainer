from __future__ import annotations

import base64

import httpx
import pytest

from training_llm_bridge.config import Settings
from training_llm_bridge.sources.intervals_client import IntervalsClient
from training_llm_bridge.utils.errors import IntervalsConfigError


def make_client(
    handler: httpx.MockTransport,
    *,
    api_key: str | None = "secret-intervals-key",
    athlete_id: str | None = "i123",
) -> IntervalsClient:
    http_client = httpx.Client(transport=handler, base_url="https://intervals.icu/api/v1")
    settings = Settings(
        intervals_api_key=api_key,
        intervals_athlete_id=athlete_id,
        intervals_api_base_url="https://intervals.icu/api/v1",
    )
    return IntervalsClient(settings=settings, client=http_client, max_retries=0)


def test_intervals_auth_uses_basic_auth() -> None:
    expected = "Basic " + base64.b64encode(b"API_KEY:secret-intervals-key").decode()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == expected
        assert request.url.path == "/api/v1/athlete/i123/profile"
        return httpx.Response(200, json={"id": "i123", "name": "Test Athlete"})

    client = make_client(httpx.MockTransport(handler))

    assert client.get_athlete()["id"] == "i123"


def test_missing_intervals_config_gives_clear_error() -> None:
    client = make_client(
        httpx.MockTransport(lambda _request: httpx.Response(200, json={})),
        api_key=None,
        athlete_id=None,
    )

    with pytest.raises(IntervalsConfigError, match="INTERVALS_API_KEY, INTERVALS_ATHLETE_ID"):
        client.list_activities()


def test_activity_listing_parses_mocked_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/athlete/i123/activities"
        assert request.url.params["oldest"] == "2026-01-01"
        assert request.url.params["newest"] == "2026-01-31"
        assert request.url.params["limit"] == "10"
        return httpx.Response(200, json=[{"id": "a1", "type": "Ride", "icu_training_load": 50}])

    client = make_client(httpx.MockTransport(handler))

    activities = client.list_activities("2026-01-01", "2026-01-31", limit=10)

    assert activities == [{"id": "a1", "type": "Ride", "icu_training_load": 50}]


def test_wellness_listing_parses_mocked_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/athlete/i123/wellness.json"
        return httpx.Response(200, json=[{"id": "2026-01-01", "ctl": 50, "atl": 45}])

    client = make_client(httpx.MockTransport(handler))

    wellness = client.list_wellness("2026-01-01", "2026-01-07")

    assert wellness[0]["ctl"] == 50


def test_events_streams_and_intervals_use_read_endpoints() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/athlete/i123/events.json":
            return httpx.Response(200, json=[{"id": 1, "name": "Sprint day"}])
        if request.url.path == "/api/v1/activity/a1/streams.json":
            assert request.url.params["types"] == "watts,heartrate"
            return httpx.Response(200, json={"watts": [100, 200]})
        if request.url.path == "/api/v1/activity/a1/intervals":
            return httpx.Response(200, json=[{"name": "30s"}])
        raise AssertionError(request.url.path)

    client = make_client(httpx.MockTransport(handler))

    assert client.list_events()[0]["name"] == "Sprint day"
    assert client.get_activity_streams("a1", stream_types=["watts", "heartrate"])["watts"] == [100, 200]
    assert client.get_activity_intervals("a1")[0]["name"] == "30s"


def test_no_intervals_write_methods_exist() -> None:
    client = make_client(httpx.MockTransport(lambda _request: httpx.Response(200, json={})))

    assert not hasattr(client, "create_event")
    assert not hasattr(client, "update_event")
    assert not hasattr(client, "create_workout")
    assert not hasattr(client, "update_wellness")
