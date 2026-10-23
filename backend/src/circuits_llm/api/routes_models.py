"""CRUD for the user's LLM endpoints (the ordered fallback chain)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import SecretStr

from circuits_llm.llm import test_endpoint
from circuits_llm.llm.contracts import EndpointTestResult, ModelEndpoint

from .schemas import EndpointIn, EndpointOrder, EndpointOut
from .services import Services, get_services

router = APIRouter(prefix="/api/models", tags=["models"])

ServicesDep = Annotated[Services, Depends(get_services)]


def _to_endpoint(
    endpoint_id: str, body: EndpointIn, existing_key: SecretStr | None
) -> ModelEndpoint:
    if body.api_key is None:
        api_key = existing_key
    else:
        api_key = SecretStr(body.api_key.strip()) if body.api_key.strip() else None
    return ModelEndpoint(
        id=endpoint_id,
        label=body.label,
        provider=body.provider,
        model=body.model,
        api_key=api_key,
        base_url=body.base_url or None,
        output_mode=body.output_mode,
        temperature=body.temperature,
        max_output_tokens=body.max_output_tokens,
        timeout_s=body.timeout_s,
        enabled=body.enabled,
    )


@router.get("")
def list_models(services: ServicesDep) -> list[EndpointOut]:
    return [EndpointOut.from_endpoint(e) for e in services.store.list_endpoints()]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_model(body: EndpointIn, services: ServicesDep) -> EndpointOut:
    endpoint = _to_endpoint(uuid.uuid4().hex[:12], body, existing_key=None)
    try:
        saved = services.store.save_endpoint(endpoint)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return EndpointOut.from_endpoint(saved)


@router.put("/order")
def reorder_models(body: EndpointOrder, services: ServicesDep) -> list[EndpointOut]:
    try:
        services.store.reorder_endpoints(body.ids)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return list_models(services)


@router.put("/{endpoint_id}")
def update_model(endpoint_id: str, body: EndpointIn, services: ServicesDep) -> EndpointOut:
    existing = services.store.get_endpoint(endpoint_id)
    saved = services.store.save_endpoint(_to_endpoint(endpoint_id, body, existing.api_key))
    return EndpointOut.from_endpoint(saved)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(endpoint_id: str, services: ServicesDep) -> Response:
    services.store.delete_endpoint(endpoint_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{endpoint_id}/test")
async def test_model(endpoint_id: str, services: ServicesDep) -> EndpointTestResult:
    endpoint = services.store.get_endpoint(endpoint_id)
    return await test_endpoint(endpoint, services.http)
