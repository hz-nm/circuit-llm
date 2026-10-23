from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import SecretStr

from circuits_llm.domain import Circuit
from circuits_llm.llm.contracts import ModelEndpoint, ProviderKind
from circuits_llm.storage import NotFoundError, Store


def _endpoint(endpoint_id: str) -> ModelEndpoint:
    return ModelEndpoint(
        id=endpoint_id,
        label=endpoint_id,
        provider=ProviderKind.OPENROUTER,
        model="openai/gpt-oss-120b",
        api_key=SecretStr(f"secret-{endpoint_id}"),
    )


def test_endpoints_round_trip_with_keys_and_order(tmp_path: Path) -> None:
    store = Store(tmp_path / "db.sqlite3")
    store.save_endpoint(_endpoint("a"))
    store.save_endpoint(_endpoint("b"))
    store.reorder_endpoints(["b", "a"])

    endpoints = store.list_endpoints()
    assert [e.id for e in endpoints] == ["b", "a"]
    assert endpoints[0].api_key is not None
    assert endpoints[0].api_key.get_secret_value() == "secret-b"
    with pytest.raises(ValueError, match="exactly once"):
        store.reorder_endpoints(["a"])


def test_versions_messages_and_cascade(tmp_path: Path, led_circuit: Circuit) -> None:
    store = Store(tmp_path / "db.sqlite3")
    project = store.create_project("Untitled circuit")
    store.add_message(project.id, "user", "make an LED circuit")
    first = store.add_version(project.id, led_circuit, "llm")
    second = store.add_version(project.id, led_circuit, "restore")

    assert (first.number, second.number) == (1, 2)
    assert store.get_project(project.id).latest_version == 2
    assert store.get_version(project.id, 1).circuit == led_circuit
    assert [v.title for v in store.list_versions(project.id)] == [led_circuit.title] * 2
    assert [m.content for m in store.list_messages(project.id)] == ["make an LED circuit"]

    store.delete_project(project.id)
    with pytest.raises(NotFoundError):
        store.get_version(project.id, 1)
