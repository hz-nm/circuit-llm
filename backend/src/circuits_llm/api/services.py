"""Long-lived application services, created once at startup and shared by all requests."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

import httpx
from fastapi import Request

from circuits_llm.settings import Settings
from circuits_llm.simulation import Simulator
from circuits_llm.storage import Store


@dataclass(frozen=True, slots=True)
class Services:
    settings: Settings
    store: Store
    http: httpx.AsyncClient
    simulator: Simulator | None
    ngspice_path: Path | None


def get_services(request: Request) -> Services:
    """FastAPI dependency returning the services attached to the app at startup."""
    return cast(Services, request.app.state.services)
