"""Comportamiento del punto de entrada: autorización previa, errores y eventos programados."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

from condo_core.errors import PROBLEM_CONTENT_TYPE, DomainError
from condo_core.testing import TENANT_A, FakeLambdaContext, claims_for, http_event
from organizaciones.handler import app, lambda_handler

Invoke = Callable[[dict[str, Any]], tuple[int, dict[str, str], Any]]


class _Cuerpo(BaseModel):
    nombre: str


# Rutas auxiliares sólo para ejercitar los manejadores de error del resolver.
@app.get("/organizaciones/__prueba/dominio")
def _ruta_error_dominio() -> None:
    raise DomainError(409, "RFC_DUPLICADO", "El RFC ya está registrado")


@app.get("/organizaciones/__prueba/validacion")
def _ruta_error_validacion() -> None:
    _Cuerpo.model_validate({})


def test_without_session_is_401_problem(invoke: Invoke) -> None:
    status, headers, body = invoke(http_event(None, request_id="req-401"))
    assert status == 401
    assert headers["Content-Type"] == PROBLEM_CONTENT_TYPE
    assert body["code"] == "NO_AUTENTICADO"
    assert body["requestId"] == "req-401"


@pytest.mark.parametrize(
    "claims",
    [claims_for("ADMIN", TENANT_A), claims_for("ASISTENTE", TENANT_A), claims_for("SUPER_ADMIN",
                                                                                   TENANT_A)],
    ids=["admin", "asistente", "super-admin-con-tenant"],
)
def test_non_super_admin_is_403(invoke: Invoke, claims: dict[str, Any]) -> None:
    status, _, body = invoke(http_event(claims))
    assert status == 403
    assert body["code"] == "PROHIBIDO"


def test_unknown_route_for_admin_is_403_not_404(invoke: Invoke) -> None:
    status, _, body = invoke(http_event(claims_for("ADMIN", TENANT_A), path="/no-existe"))
    assert (status, body["code"]) == (403, "PROHIBIDO")


def test_unknown_route_for_super_admin_is_404_problem(invoke: Invoke) -> None:
    status, headers, body = invoke(
        http_event(claims_for("SUPER_ADMIN"), path="/organizaciones/no-existe")
    )
    assert status == 404
    assert headers["Content-Type"] == PROBLEM_CONTENT_TYPE
    assert body["code"] == "NO_ENCONTRADA"


def test_domain_error_becomes_problem(invoke: Invoke) -> None:
    status, _, body = invoke(
        http_event(claims_for("SUPER_ADMIN"), path="/organizaciones/__prueba/dominio",
                   request_id="req-dom")
    )
    assert (status, body["code"], body["requestId"]) == (409, "RFC_DUPLICADO", "req-dom")


def test_validation_error_becomes_400(invoke: Invoke) -> None:
    status, _, body = invoke(
        http_event(claims_for("SUPER_ADMIN"), path="/organizaciones/__prueba/validacion")
    )
    assert (status, body["code"]) == (400, "VALIDACION")
    assert body["errores"][0]["campo"] == "nombre"


def test_scheduled_event_goes_to_reconciler() -> None:
    event = {"source": "aws.events", "detail-type": "Scheduled Event"}
    assert lambda_handler(event, FakeLambdaContext()) == {"reconciliadas": 0}
