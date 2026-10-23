"""Manual live smoke test of the design loop against real providers.

Reads API keys from ``backend/.env`` (gitignored). Costs real tokens, so it is
never run by the test suite. Usage::

    python scripts/smoke_live.py "Design an RC low-pass at 1 kHz" [openrouter|gemini] [model]
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import httpx
from pydantic import SecretStr

from circuits_llm.domain import Circuit, Issue
from circuits_llm.llm import DesignCompleted, DesignRequest, ModelEndpoint, ProviderKind, run_design

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"
DEFAULT_MODELS = {"openrouter": "openai/gpt-oss-120b:free", "gemini": "gemini-3.8-flash"}
KEY_VARS = {"openrouter": "OPENROUTER_API_KEY", "gemini": "GEMINI_API_KEY"}
PROVIDERS = {"openrouter": ProviderKind.OPENROUTER, "gemini": ProviderKind.GEMINI}


def _read_env() -> dict[str, str]:
    pairs = (
        line.split("=", 1)
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    )
    return {key.strip(): value.strip() for key, value in pairs}


async def _simulation_check() -> list[object]:
    try:
        from circuits_llm.simulation import NgspiceSimulator, locate_ngspice, simulation_issues
    except ImportError:
        return []
    path = locate_ngspice()
    if path is None:
        return []
    simulator = NgspiceSimulator(path)

    async def check(circuit: Circuit) -> list[Issue]:
        return await simulation_issues(simulator, circuit)

    return [check]


async def main() -> None:
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Design an RC low-pass filter at 1 kHz."
    which = sys.argv[2] if len(sys.argv) > 2 else "openrouter"
    model = sys.argv[3] if len(sys.argv) > 3 else DEFAULT_MODELS[which]
    key = _read_env().get(KEY_VARS[which])
    if not key:
        raise SystemExit(f"{KEY_VARS[which]} is not set in {ENV_FILE}")

    endpoint = ModelEndpoint(
        id=which,
        label=which,
        provider=PROVIDERS[which],
        model=model,
        api_key=SecretStr(key),
        max_output_tokens=16_384,
    )
    checks = await _simulation_check()
    started = time.monotonic()
    async with httpx.AsyncClient() as client:
        async for event in run_design(
            DesignRequest(user_message=prompt),
            [endpoint],
            client=client,
            extra_checks=checks,  # type: ignore[arg-type]
        ):
            if isinstance(event, DesignCompleted):
                print(f"\nCOMPLETED in {time.monotonic() - started:.1f}s\n{event.reply}\n")
                if event.circuit is not None:
                    print(event.circuit.model_dump_json(indent=1, exclude_defaults=True))
                for warning in event.warnings:
                    print("warning:", warning.message)
            else:
                print(event.model_dump_json())


if __name__ == "__main__":
    asyncio.run(main())
