"""Health and component-catalog endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from circuits_llm import __version__
from circuits_llm.domain import CATALOG

from .schemas import ComponentSpecOut, HealthOut, NgspiceStatus, PinOut
from .services import Services, get_services

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(services: Annotated[Services, Depends(get_services)]) -> HealthOut:
    path = services.ngspice_path
    return HealthOut(
        version=__version__,
        ngspice=NgspiceStatus(available=services.simulator is not None, path=path and str(path)),
    )


@router.get("/catalog")
def catalog() -> list[ComponentSpecOut]:
    return [
        ComponentSpecOut(
            kind=spec.kind,
            display_name=spec.display_name,
            category=spec.category,
            designator_prefix=spec.designator_prefix,
            description=spec.description,
            pins=[
                PinOut(name=p.name, description=p.description, optional=p.optional)
                for p in spec.pins
            ],
            value_unit=spec.value_unit,
            value_required=spec.value_required,
            models=list(spec.models),
            default_model=spec.default_model,
        )
        for spec in CATALOG.values()
    ]
