from __future__ import annotations

import json
from pathlib import Path

import pytest

from training_llm_bridge import cli
from training_llm_bridge.coach.sprint_constraints import get_sprint_kilo_constraints


def test_sprint_constraints_include_required_archetypes() -> None:
    constraints = get_sprint_kilo_constraints()

    assert "low-volume heavy lower body" in constraints["routine_archetypes"]
    assert "posterior-chain maintenance" in constraints["routine_archetypes"]
    assert "Do not create a generic bodybuilding program unless explicitly requested." in constraints[
        "principles"
    ]


def test_cli_constraints_outputs_json(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = cli.main(["constraints", "sprint-kilo"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["sport_context"] == "cycling sprint and kilo performance"


def test_cli_create_routine_dry_run_uses_mocked_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payload_path = tmp_path / "routine.json"
    payload_path.write_text(json.dumps({"title": "Dry run", "exercises": []}), encoding="utf-8")

    class FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> "FakeClient":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def create_routine(self, payload: dict, dry_run: bool = True) -> dict:
            assert dry_run is True
            return {"dry_run": True, "payload": {"routine": payload}}

    monkeypatch.setattr(cli, "HevyClient", FakeClient)

    exit_code = cli.main(["create-routine", str(payload_path), "--dry-run"])

    captured = capsys.readouterr()
    result = json.loads(captured.out)

    assert exit_code == 0
    assert result["dry_run"] is True
    assert result["payload"]["routine"]["title"] == "Dry run"
