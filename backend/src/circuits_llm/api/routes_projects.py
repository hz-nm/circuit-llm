"""Projects, chat turns (streamed as Server-Sent Events), circuit versions and simulation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

from circuits_llm.domain import Circuit, Issue, Severity, check_circuit, to_mermaid
from circuits_llm.llm import run_design
from circuits_llm.llm.contracts import (
    MAX_HISTORY_TURNS,
    ChatTurn,
    DesignCompleted,
    DesignFailed,
    DesignRequest,
)
from circuits_llm.simulation import SimulationResult, Simulator, SpiceEmissionError, to_spice
from circuits_llm.storage import MessageMeta, MessageRecord, ProjectRecord, VersionRecord

from .schemas import (
    CircuitIn,
    MessageIn,
    ProjectCreate,
    ProjectDetail,
    ProjectRename,
    TurnSaved,
    VersionOut,
)
from .services import Services, get_services

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["projects"])

ServicesDep = Annotated[Services, Depends(get_services)]

DEFAULT_TITLE: Final = ProjectCreate.model_fields["title"].default
_SSE_HEADERS: Final = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
INTERRUPTED_REPLY: Final = "Stopped before an answer was ready."


def version_out(record: VersionRecord) -> VersionOut:
    circuit = record.circuit
    return VersionOut.from_record(record, check_circuit(circuit), to_mermaid(circuit))


# --------------------------------------------------------------------------- projects


@router.get("")
def list_projects(services: ServicesDep) -> list[ProjectRecord]:
    return services.store.list_projects()


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreate, services: ServicesDep) -> ProjectRecord:
    return services.store.create_project(body.title)


@router.get("/{project_id}")
def get_project(project_id: str, services: ServicesDep) -> ProjectDetail:
    store = services.store
    project = store.get_project(project_id)
    latest = store.latest_version(project_id)
    return ProjectDetail(
        project=project,
        messages=store.list_messages(project_id),
        versions=store.list_versions(project_id),
        latest=version_out(latest) if latest else None,
    )


@router.patch("/{project_id}")
def rename_project(project_id: str, body: ProjectRename, services: ServicesDep) -> ProjectRecord:
    return services.store.rename_project(project_id, body.title)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, services: ServicesDep) -> Response:
    services.store.delete_project(project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- versions


@router.get("/{project_id}/versions/{number}")
def get_version(project_id: str, number: int, services: ServicesDep) -> VersionOut:
    return version_out(services.store.get_version(project_id, number))


@router.put("/{project_id}/circuit", status_code=status.HTTP_201_CREATED)
def save_manual_edit(project_id: str, body: CircuitIn, services: ServicesDep) -> VersionOut:
    """Store a hand-edited circuit as a new version (saved even if it has ERC errors)."""
    services.store.get_project(project_id)
    return version_out(services.store.add_version(project_id, body.circuit, "manual"))


@router.post("/{project_id}/versions/{number}/restore", status_code=status.HTTP_201_CREATED)
def restore_version(project_id: str, number: int, services: ServicesDep) -> VersionOut:
    old = services.store.get_version(project_id, number)
    return version_out(services.store.add_version(project_id, old.circuit, "restore"))


@router.get("/{project_id}/versions/{number}/simulation")
def get_simulation(project_id: str, number: int, services: ServicesDep) -> SimulationResult:
    result = services.store.get_simulation(project_id, number)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "this version has not been simulated yet")
    return result


@router.post("/{project_id}/versions/{number}/simulate")
async def simulate_version(project_id: str, number: int, services: ServicesDep) -> SimulationResult:
    simulator = _require_simulator(services)
    record = await asyncio.to_thread(services.store.get_version, project_id, number)
    errors = [i for i in check_circuit(record.circuit) if i.severity is Severity.ERROR]
    if errors:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "fix the circuit's ERC errors before simulating: "
            + "; ".join(issue.message for issue in errors),
        )
    result = await simulator.simulate(record.circuit)
    await asyncio.to_thread(services.store.save_simulation, project_id, number, result)
    return result


@router.get(
    "/{project_id}/versions/{number}/spice",
    response_class=PlainTextResponse,
    responses={200: {"content": {"text/plain": {"schema": {"type": "string"}}}}},
)
def export_spice(project_id: str, number: int, services: ServicesDep) -> PlainTextResponse:
    """The ngspice deck for a version, for use in other simulators or for debugging."""
    record = services.store.get_version(project_id, number)
    try:
        deck = to_spice(record.circuit)
    except SpiceEmissionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return PlainTextResponse(deck.text)


def _require_simulator(services: Services) -> Simulator:
    if services.simulator is None:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "ngspice was not found; install it or set CIRCUITS_LLM_NGSPICE_PATH",
        )
    return services.simulator


# --------------------------------------------------------------------------- chat turns


class _SimulationCheck:
    """Design-loop check that simulates candidates and remembers the last result.

    A circuit that fails to simulate is sent back to the LLM for repair; the
    successful result is kept so the accepted version needn't be simulated twice.
    """

    def __init__(self, simulator: Simulator) -> None:
        self._simulator = simulator
        self._last: tuple[Circuit, SimulationResult] | None = None

    async def __call__(self, circuit: Circuit) -> list[Issue]:
        result = await self._simulator.simulate(circuit)
        self._last = (circuit, result)
        if result.ok:
            return []
        return [
            Issue(
                severity=Severity.ERROR,
                code="simulation_failed",
                message=f"The simulator rejected the circuit: {result.error}",
            )
        ]

    def result_for(self, circuit: Circuit) -> SimulationResult | None:
        if self._last is not None and self._last[0] == circuit:
            return self._last[1]
        return None


def _sse(event: BaseModel) -> str:
    event_type = getattr(event, "type", "message")
    return f"event: {event_type}\ndata: {event.model_dump_json()}\n\n"


@router.post(
    "/{project_id}/messages",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "Server-Sent Events; each `data:` line is a StreamEvent.",
            "content": {
                "text/event-stream": {"schema": {"$ref": "#/components/schemas/StreamEvent"}}
            },
        }
    },
)
async def send_message(
    project_id: str, body: MessageIn, services: ServicesDep
) -> StreamingResponse:
    project = await asyncio.to_thread(services.store.get_project, project_id)  # 404 early
    return StreamingResponse(
        _design_turn(services, project, body.content),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )


async def _design_turn(
    services: Services, project: ProjectRecord, content: str
) -> AsyncIterator[str]:
    store = services.store
    current = await asyncio.to_thread(store.latest_version, project.id)
    previous = await asyncio.to_thread(store.list_messages, project.id)
    history = [ChatTurn(role=m.role, content=m.content) for m in previous if not m.meta.error][
        -MAX_HISTORY_TURNS:
    ]
    user_message = await asyncio.to_thread(store.add_message, project.id, "user", content)

    endpoints = await asyncio.to_thread(store.list_endpoints)
    sim_check = (
        _SimulationCheck(services.simulator)
        if services.simulator is not None and services.settings.simulate_during_design
        else None
    )
    checks: list[Callable[[Circuit], Awaitable[list[Issue]]]] = [sim_check] if sim_check else []
    request = DesignRequest(
        user_message=content,
        history=history,
        current_circuit=current.circuit if current else None,
    )

    outcome: DesignCompleted | DesignFailed = DesignFailed(
        error="the design run ended unexpectedly"
    )
    try:
        async for event in run_design(
            request, endpoints, client=services.http, extra_checks=checks
        ):
            if isinstance(event, DesignCompleted | DesignFailed):
                outcome = event
            yield _sse(event)
    except (asyncio.CancelledError, GeneratorExit):
        # The client went away mid-turn. Record that so history stays consistent; this is a
        # quick local write, done synchronously because we may not await while cancelling.
        services.store.add_message(
            project.id, "assistant", INTERRUPTED_REPLY, meta=MessageMeta(error=True)
        )
        raise
    except Exception:
        logger.exception("design turn failed for project %s", project.id)
        outcome = DesignFailed(error="internal error while designing; see the server log")
        yield _sse(outcome)

    assistant_message, version = await asyncio.to_thread(
        _persist_turn, services, project, current, outcome, sim_check
    )
    yield _sse(
        TurnSaved(user_message=user_message, assistant_message=assistant_message, version=version)
    )


def _persist_turn(
    services: Services,
    project: ProjectRecord,
    current: VersionRecord | None,
    outcome: DesignCompleted | DesignFailed,
    sim_check: _SimulationCheck | None,
) -> tuple[MessageRecord, VersionOut | None]:
    """Save the assistant reply (and the new circuit version, if it changed)."""
    store = services.store
    if isinstance(outcome, DesignFailed):
        message = store.add_message(
            project.id, "assistant", outcome.error, meta=MessageMeta(error=True)
        )
        return message, None

    version: VersionOut | None = None
    circuit = outcome.circuit
    if circuit is not None and (current is None or circuit != current.circuit):
        record = store.add_version(project.id, circuit, "llm")
        if sim_check is not None and (result := sim_check.result_for(circuit)) is not None:
            store.save_simulation(project.id, record.number, result)
        if project.title == DEFAULT_TITLE:
            store.rename_project(project.id, circuit.title)
        version = version_out(record)

    message = store.add_message(
        project.id,
        "assistant",
        outcome.reply,
        version_number=version.number if version else None,
        meta=MessageMeta(
            endpoint_id=outcome.endpoint_id, model=outcome.model, warnings=outcome.warnings
        ),
    )
    return message, version
