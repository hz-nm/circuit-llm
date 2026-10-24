"""The generate → parse → validate → repair loop with an endpoint fallback chain.

``run_design`` is an async generator of :data:`DesignEvent`. It always ends with
exactly one terminal event (``DesignCompleted`` or ``DesignFailed``) unless the
consumer stops iterating, in which case closing the generator cancels any
in-flight request cleanly (nothing here swallows ``CancelledError``).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Sequence
from contextlib import aclosing
from typing import Any, Final

import httpx

from circuits_llm.domain import Circuit, Issue, Severity

from .contracts import (
    AttemptStarted,
    DesignCompleted,
    DesignEvent,
    DesignFailed,
    DesignRequest,
    EndpointFailed,
    ModelEndpoint,
    Planned,
    ValidationFailed,
)
from .parsing import parse_model_output
from .planner import (
    Plan,
    build_planner_messages,
    fallback_plan,
    ordered,
    parse_plan,
    planner_response_schema,
)
from .prompts import build_messages, build_repair_messages, response_schema
from .providers.base import Completion, Message, Provider, ProviderError
from .providers.factory import ProviderFactory, create_provider

logger = logging.getLogger(__name__)

MAX_ATTEMPTS_PER_ENDPOINT: Final = 3
MAX_ENDPOINTS: Final = 10
MAX_PROVIDER_TRIES: Final = 2  # one retry of a retryable provider error before failing over
RETRY_BACKOFF_S: Final = 1.5
MAX_FAILURE_SUMMARY_CHARS: Final = 400
MAX_PROBLEMS_IN_ERROR: Final = 3

ExtraCheck = Callable[[Circuit], Awaitable[list[Issue]]]


async def run_design(
    request: DesignRequest,
    endpoints: Sequence[ModelEndpoint],
    *,
    client: httpx.AsyncClient,
    extra_checks: Sequence[ExtraCheck] = (),
    provider_factory: ProviderFactory = create_provider,
    plan_first: bool = True,
) -> AsyncIterator[DesignEvent]:
    """Design (or answer about) a circuit, trying each enabled endpoint in order.

    With ``plan_first`` the first endpoint that answers also plans the design: it picks
    the component families (so the designer prompt only describes those) and sketches
    the circuit. Without it, or when the plan is unusable, every family is described.
    """
    enabled = [e for e in endpoints if e.enabled][:MAX_ENDPOINTS]
    if not enabled:
        yield DesignFailed(
            error="No model is configured. Add and enable a model in Settings to start designing."
        )
        return

    plan: Plan | None = None if plan_first else fallback_plan()
    failures: list[str] = []
    for endpoint in enabled:
        provider = provider_factory(endpoint, client)
        if plan is None:
            try:
                plan = await _make_plan(provider, request, endpoint.id)
            except ProviderError as exc:
                logger.info("endpoint %s failed while planning: %s", endpoint.id, exc.kind.value)
                yield EndpointFailed(endpoint_id=endpoint.id, error=exc.message)
                failures.append(f"{endpoint.label} ({endpoint.model}): {exc.message}")
                continue
            yield Planned(
                endpoint_id=endpoint.id,
                families=ordered(plan.families),
                plan=plan.text,
                fallback=plan.fallback,
            )
        base = build_messages(request, plan.families, plan.text)
        attempts = _run_endpoint(endpoint, provider, base, extra_checks)
        async with aclosing(attempts) as events:
            async for event in events:
                yield event
                if isinstance(event, DesignCompleted):
                    return
                if isinstance(event, EndpointFailed):
                    failures.append(f"{endpoint.label} ({endpoint.model}): {event.error}")
    yield DesignFailed(error=_failure_summary(failures))


async def _run_endpoint(
    endpoint: ModelEndpoint,
    provider: Provider,
    base: Sequence[Message],
    extra_checks: Sequence[ExtraCheck],
) -> AsyncGenerator[DesignEvent, None]:
    """Up to ``MAX_ATTEMPTS_PER_ENDPOINT`` rounds; ends with DesignCompleted or EndpointFailed."""
    messages: list[Message] = list(base)
    problems: list[str] = []
    for attempt in range(1, MAX_ATTEMPTS_PER_ENDPOINT + 1):
        yield AttemptStarted(
            endpoint_id=endpoint.id,
            endpoint_label=endpoint.label,
            model=endpoint.model,
            attempt=attempt,
            max_attempts=MAX_ATTEMPTS_PER_ENDPOINT,
        )
        try:
            completion = await _complete_with_retry(provider, messages, endpoint.id)
        except ProviderError as exc:
            logger.info("endpoint %s failed: %s", endpoint.id, exc.kind.value)
            yield EndpointFailed(endpoint_id=endpoint.id, error=exc.message)
            return
        logger.debug("endpoint %s raw answer: %.2000s", endpoint.id, completion.text)

        parsed = parse_model_output(completion.text)
        problems = list(parsed.problems)
        warnings = list(parsed.warnings)
        if parsed.circuit is not None and extra_checks:
            issues = await _run_extra_checks(parsed.circuit, extra_checks)
            problems = [i.message for i in issues if i.severity is Severity.ERROR]
            warnings += [i for i in issues if i.severity is Severity.WARNING]
        if not problems:
            logger.info("endpoint %s produced a valid answer on attempt %d", endpoint.id, attempt)
            yield DesignCompleted(
                reply=parsed.reply,
                circuit=parsed.circuit,
                warnings=warnings,
                endpoint_id=endpoint.id,
                model=endpoint.model,
            )
            return

        logger.info("endpoint %s attempt %d: %d problem(s)", endpoint.id, attempt, len(problems))
        if attempt < MAX_ATTEMPTS_PER_ENDPOINT:
            yield ValidationFailed(endpoint_id=endpoint.id, attempt=attempt, problems=problems)
            messages = build_repair_messages(base, completion.text, problems)

    shown = "; ".join(problems[:MAX_PROBLEMS_IN_ERROR])
    more = (
        f" (+{len(problems) - MAX_PROBLEMS_IN_ERROR} more)"
        if len(problems) > MAX_PROBLEMS_IN_ERROR
        else ""
    )
    yield EndpointFailed(
        endpoint_id=endpoint.id,
        error=(f"Answer still invalid after {MAX_ATTEMPTS_PER_ENDPOINT} attempts: {shown}{more}"),
    )


async def _complete_with_retry(
    provider: Provider,
    messages: Sequence[Message],
    endpoint_id: str,
    schema: dict[str, Any] | None = None,
) -> Completion:
    """Call the provider, retrying a retryable error once after a short backoff."""
    for attempt in range(1, MAX_PROVIDER_TRIES + 1):
        try:
            return await provider.complete(
                messages, response_schema=schema if schema is not None else response_schema()
            )
        except ProviderError as exc:
            if not exc.retryable or attempt == MAX_PROVIDER_TRIES:
                raise
            logger.info(
                "endpoint %s: retryable %s error, retrying in %.1f s",
                endpoint_id,
                exc.kind.value,
                RETRY_BACKOFF_S,
            )
            await asyncio.sleep(RETRY_BACKOFF_S)
    raise AssertionError("unreachable: the retry loop always returns or raises")


async def _make_plan(provider: Provider, request: DesignRequest, endpoint_id: str) -> Plan:
    completion = await _complete_with_retry(
        provider, build_planner_messages(request), endpoint_id, planner_response_schema()
    )
    plan = parse_plan(completion.text, request.current_circuit)
    if plan.fallback:
        logger.info("endpoint %s: unusable plan, describing every family", endpoint_id)
    return plan


async def _run_extra_checks(circuit: Circuit, checks: Sequence[ExtraCheck]) -> list[Issue]:
    """Run the caller's checks (e.g. a simulation smoke test) after the ERC has passed.

    A check that crashes is a bug on our side, not the model's, so it becomes a
    warning instead of triggering a repair round.
    """
    issues: list[Issue] = []
    for check in checks:
        try:
            issues.extend(await check(circuit))
        except Exception as exc:  # plug-in boundary: never let a check kill the stream
            logger.exception("extra check %r failed", check)
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    code="check_failed",
                    message=f"An internal check could not run: {type(exc).__name__}.",
                )
            )
    return issues


def _failure_summary(failures: Sequence[str]) -> str:
    lines = [f"- {f[:MAX_FAILURE_SUMMARY_CHARS]}" for f in failures]
    return "No model produced a valid answer.\n" + "\n".join(lines)
