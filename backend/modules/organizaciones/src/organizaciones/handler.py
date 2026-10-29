"""Punto de entrada único del módulo organizaciones (principio II).

Una sola Lambda atiende dos tipos de evento:

- Peticiones HTTP de la HTTP API: se exige SUPER_ADMIN **antes** de resolver la ruta, de leer el
  cuerpo o de consultar datos (FR-001, FR-002). Así, para cualquier otro rol, una ruta inexistente
  y una existente responden igual.
- Eventos programados de EventBridge (``source == "aws.events"``): el reconciliador de altas.
"""

from __future__ import annotations

import json
from typing import Any

from aws_lambda_powertools.event_handler import APIGatewayHttpResolver, Response
from pydantic import ValidationError

from condo_core.auth import SUPER_ADMIN, claims_from_event, require_role
from condo_core.errors import PROBLEM_CONTENT_TYPE, DomainError, from_validation_error
from condo_core.logging import bind_request, inject_lambda_context, logger
from organizaciones import provisioning
from organizaciones.routes import router

app = APIGatewayHttpResolver()
app.include_router(router)


def _problem(error: DomainError) -> Response[str]:
    request_id = app.current_event.request_context.request_id
    return Response(
        status_code=error.status,
        content_type=PROBLEM_CONTENT_TYPE,
        body=json.dumps(error.to_problem(request_id), ensure_ascii=False),
    )


@app.exception_handler(DomainError)
def _handle_domain_error(error: DomainError) -> Response[str]:
    logger.info("error_de_dominio", extra={"code": error.code, "status": error.status})
    return _problem(error)


@app.exception_handler(ValidationError)
def _handle_validation_error(error: ValidationError) -> Response[str]:
    domain_error = from_validation_error(error)
    logger.info("error_de_validacion", extra={"code": domain_error.code})
    return _problem(domain_error)


@app.not_found
def _handle_not_found(_: Exception) -> Response[str]:
    return _problem(DomainError(404, "NO_ENCONTRADA", "Recurso no encontrado"))


def on_schedule(event: dict[str, Any]) -> dict[str, Any]:
    """Evento programado de EventBridge: reconciliador de altas atascadas (SC-006)."""
    return {"reconciliadas": provisioning.reconcile_stale()}


@inject_lambda_context()
def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    if event.get("source") == "aws.events":
        return on_schedule(event)

    claims = claims_from_event(event)
    bind_request(event, claims, lambda_request_id=getattr(context, "aws_request_id", None))
    try:
        require_role(claims, SUPER_ADMIN)
    except DomainError as error:
        logger.info("acceso_rechazado", extra={"code": error.code})
        return error.to_response(event.get("requestContext", {}).get("requestId"))
    return app.resolve(event, context)
