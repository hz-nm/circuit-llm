from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from circuits_llm.domain import Circuit, Issue
from circuits_llm.llm import (
    AttemptStarted,
    Completion,
    DesignCompleted,
    DesignEvent,
    DesignFailed,
    DesignRequest,
    EndpointFailed,
    ErrorKind,
    ExtraCheck,
    Message,
    ModelEndpoint,
    Planned,
    Provider,
    ProviderError,
    ProviderKind,
    ValidationFailed,
    run_design,
)
from circuits_llm.llm.prompts import FEW_SHOT_EXAMPLES
from circuits_llm.simulation import NgspiceSimulator, locate_ngspice, simulation_issues

VALID_ANSWER = json.dumps(FEW_SHOT_EXAMPLES[0][1])
NO_GROUND = json.dumps(
    {
        "reply": "oops",
        "circuit": {
            "title": "t",
            "components": [
                {"id": "R1", "kind": "resistor", "value": 1, "pins": {"1": "A", "2": "B"}}
            ],
        },
    }
)


class FakeProvider:
    """Replays scripted answers (strings) or errors, recording the messages it was sent."""

    def __init__(self, script: Sequence[str | ProviderError]) -> None:
        self.script = list(script)
        self.calls: list[list[Message]] = []

    async def complete(
        self, messages: Sequence[Message], *, response_schema: dict[str, Any] | None
    ) -> Completion:
        self.calls.append(list(messages))
        step = self.script.pop(0)
        if isinstance(step, ProviderError):
            raise step
        return Completion(text=step, finish_reason="stop")


def _endpoint(endpoint_id: str) -> ModelEndpoint:
    return ModelEndpoint(
        id=endpoint_id, label=endpoint_id, provider=ProviderKind.OPENAI_COMPATIBLE, model="m"
    )


def _run(
    providers: dict[str, FakeProvider],
    request: DesignRequest | None = None,
    *,
    plan_first: bool = False,
    extra_checks: Sequence[ExtraCheck] = (),
) -> list[DesignEvent]:
    def factory(endpoint: ModelEndpoint, client: httpx.AsyncClient) -> Provider:
        return providers[endpoint.id]

    async def collect() -> list[DesignEvent]:
        async with httpx.AsyncClient() as client:
            stream = run_design(
                request or DesignRequest(user_message="Light an LED"),
                [_endpoint(i) for i in providers],
                client=client,
                provider_factory=factory,
                plan_first=plan_first,
                extra_checks=extra_checks,
            )
            return [event async for event in stream]

    return asyncio.run(collect())


def test_repair_then_success() -> None:
    provider = FakeProvider([NO_GROUND, VALID_ANSWER])
    events = _run({"a": provider})
    assert [type(e) for e in events] == [
        AttemptStarted,
        ValidationFailed,
        AttemptStarted,
        DesignCompleted,
    ]
    assert isinstance(events[1], ValidationFailed) and "ground" in events[1].problems[0]
    repair = provider.calls[1]
    assert (repair[-2].role, repair[-2].content) == ("assistant", NO_GROUND)
    assert repair[-1].content.startswith("Your answer has 1 problem(s):\n1. ")
    done = events[-1]
    assert isinstance(done, DesignCompleted) and done.circuit is not None


def test_fallback_to_second_endpoint_after_provider_error() -> None:
    auth = ProviderError(ErrorKind.AUTH, "bad key", status_code=401)
    events = _run({"a": FakeProvider([auth]), "b": FakeProvider([VALID_ANSWER])})
    assert [type(e) for e in events] == [
        AttemptStarted,
        EndpointFailed,
        AttemptStarted,
        DesignCompleted,
    ]
    assert isinstance(events[-1], DesignCompleted) and events[-1].endpoint_id == "b"


def test_question_only_reply_and_exhausted_endpoint() -> None:
    answer = '{"reply": "It limits the LED current.", "circuit": null}'
    events = _run({"a": FakeProvider([answer])})
    done = events[-1]
    assert isinstance(done, DesignCompleted)
    assert (done.reply, done.circuit) == ("It limits the LED current.", None)

    failed = _run({"a": FakeProvider([NO_GROUND] * 3)})
    assert sum(isinstance(e, AttemptStarted) for e in failed) == 3
    assert isinstance(failed[-1], DesignFailed) and "after 3 attempts" in failed[-1].error
    assert "Settings" in _no_endpoint_error()


def _no_endpoint_error() -> str:
    events = _run({})
    assert len(events) == 1 and isinstance(events[0], DesignFailed)
    return events[0].error


def test_planner_narrows_the_designer_prompt() -> None:
    plan = json.dumps({"families": ["Gates"], "plan": "1. Schmitt inverter on a divider."})
    provider = FakeProvider([f"Sure!\n```json\n{plan}\n```", VALID_ANSWER])

    events = _run({"a": provider}, plan_first=True)

    planned = events[0]
    assert isinstance(planned, Planned)
    assert planned.families == ["core", "logic"]  # alias resolved, core always included
    assert isinstance(events[-1], DesignCompleted)
    designer_system, *_, designer_user = provider.calls[1]
    assert '"schmitt_inverter"' in designer_system.content
    assert '"npn"' not in designer_system.content  # transistors were not chosen
    assert "Schmitt inverter on a divider" in designer_user.content


def test_unusable_plan_falls_back_to_every_family() -> None:
    provider = FakeProvider(["I think you need some gates.", VALID_ANSWER])

    events = _run({"a": provider}, plan_first=True)

    planned = events[0]
    assert isinstance(planned, Planned) and planned.fallback
    assert '"npn"' in provider.calls[1][0].content
    assert isinstance(events[-1], DesignCompleted)


def test_unprogrammed_arduino_gets_a_focused_follow_up() -> None:
    answer = json.loads(json.dumps(FEW_SHOT_EXAMPLES[-1][1]))  # the Arduino night light
    arduino = answer["circuit"]["components"][0]
    assert arduino["kind"] == "arduino_uno"
    del arduino["behavior"]  # what weak models do
    fill = '{"behavior": [{"pin": "D9", "output": "rule", "when": "A0 > 2.5"}]}'
    provider = FakeProvider([json.dumps(answer), fill])

    events = _run({"a": provider}, DesignRequest(user_message="Arduino night light"))

    completed = events[-1]
    assert isinstance(completed, DesignCompleted) and completed.circuit is not None
    assert completed.circuit.components[0].behavior is not None
    assert [type(e) for e in events].count(AttemptStarted) == 1  # no repair round needed
    question = provider.calls[1][-1].content
    assert "D9 -> net PIN9" in question and "A0 -> net SENSE" in question


@pytest.mark.skipif(locate_ngspice() is None, reason="ngspice not found")
def test_static_sensor_gets_a_focused_stimulus_fix() -> None:
    # The LDR street lamp with its light profile removed: "lamp on at night" can never
    # be exercised, so the loop asks for the sensor's stimulus instead of a full repair.
    answer = json.loads(json.dumps(next(a for r, a, _ in FEW_SHOT_EXAMPLES if "dusk" in r)))
    ldr = next(c for c in answer["circuit"]["components"] if c["kind"] == "ldr")
    del ldr["stimulus"]
    profile = '{"stimulus": {"shape": "pwl", "points": [[0, 1000], [0.5, 0.5], [1, 1000]]}}'
    provider = FakeProvider([json.dumps(answer), profile])
    simulator = NgspiceSimulator(cast(Path, locate_ngspice()))

    async def simulate(circuit: Circuit) -> list[Issue]:
        return await simulation_issues(simulator, circuit)

    events = _run({"a": provider}, extra_checks=[simulate])

    completed = events[-1]
    assert isinstance(completed, DesignCompleted), events[-1]
    assert completed.circuit is not None
    assert [type(e) for e in events].count(AttemptStarted) == 1  # fixed without a repair round
    assert "LDR1" in provider.calls[1][-1].content
