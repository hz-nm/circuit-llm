from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

import httpx

from circuits_llm.llm import (
    AttemptStarted,
    Completion,
    DesignCompleted,
    DesignEvent,
    DesignFailed,
    DesignRequest,
    EndpointFailed,
    ErrorKind,
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
