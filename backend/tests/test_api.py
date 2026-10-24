from __future__ import annotations

import json
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from circuits_llm.api import create_app, routes_projects
from circuits_llm.domain import Circuit
from circuits_llm.llm.contracts import AttemptStarted, DesignCompleted, DesignEvent
from circuits_llm.settings import Settings


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    settings = Settings(data_dir=tmp_path, simulate_during_design=False)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def _events(body: str) -> list[dict[str, Any]]:
    return [
        json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")
    ]


def test_chat_turn_creates_version_and_simulates(
    client: TestClient, led_circuit: Circuit, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run_design(*_: object, **__: object) -> AsyncIterator[DesignEvent]:
        yield AttemptStarted(
            endpoint_id="e1", endpoint_label="fake", model="m", attempt=1, max_attempts=3
        )
        yield DesignCompleted(
            reply="Here you go.", circuit=led_circuit, endpoint_id="e1", model="m"
        )

    monkeypatch.setattr(routes_projects, "run_design", fake_run_design)

    project = client.post("/api/projects", json={}).json()
    response = client.post(
        f"/api/projects/{project['id']}/messages", json={"content": "LED please"}
    )
    assert response.status_code == 200
    events = _events(response.text)
    assert [e["type"] for e in events] == ["attempt_started", "completed", "saved"]
    assert events[-1]["version"]["number"] == 1

    detail = client.get(f"/api/projects/{project['id']}").json()
    assert detail["project"]["title"] == led_circuit.title  # auto-renamed from the default
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert "flowchart" in detail["latest"]["mermaid"]

    if not client.get("/api/health").json()["ngspice"]["available"]:
        pytest.skip("ngspice not installed")
    result = client.post(f"/api/projects/{project['id']}/versions/1/simulate").json()
    assert result["ok"], result["error"]
    assert client.get(f"/api/projects/{project['id']}/versions/1/simulation").status_code == 200


def test_model_keys_are_never_returned(client: TestClient) -> None:
    body = {"label": "OR", "provider": "openrouter", "model": "x/y", "api_key": "sk-secret-123456"}
    created = client.post("/api/models", json=body).json()
    assert created["has_api_key"] and created["api_key_hint"] == "…3456"
    assert "sk-secret" not in client.get("/api/models").text

    kept = client.put(f"/api/models/{created['id']}", json={**body, "api_key": None}).json()
    assert kept["has_api_key"]


def test_run_bar_override_adds_transient_with_all_nodes(
    client: TestClient, led_circuit: Circuit
) -> None:
    if not client.get("/api/health").json()["ngspice"]["available"]:
        pytest.skip("ngspice not installed")
    project = client.post("/api/projects", json={}).json()
    circuit = led_circuit.model_dump(mode="json")
    client.put(f"/api/projects/{project['id']}/circuit", json={"circuit": circuit})

    result = client.post(
        f"/api/projects/{project['id']}/versions/1/simulate",
        json={"stop_time": 1e-3, "step_time": 1e-5},
    ).json()

    assert result["ok"], result["error"]
    tran = next(a for a in result["analyses"] if a["type"] == "tran")
    assert tran["x"]["values"][-1] == pytest.approx(1e-3)
    nets = {t["net"]: t["probed"] for t in tran["traces"] if t["net"]}
    assert nets == {"N1": True, "VCC": False}  # every net recorded; only probes plotted
