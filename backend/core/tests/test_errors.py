from __future__ import annotations

import json

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from condo_core.errors import (
    PROBLEM_CONTENT_TYPE,
    DomainError,
    FieldError,
    forbidden,
    from_validation_error,
    not_authenticated,
)


class _Modelo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str
    edad: int


def _validation_error(data: dict[str, object]) -> ValidationError:
    with pytest.raises(ValidationError) as exc:
        _Modelo.model_validate(data)
    return exc.value


def test_problem_has_rfc9457_fields() -> None:
    error = DomainError(409, "RFC_DUPLICADO", "El RFC ya está registrado", detail="detalle")
    assert error.to_problem("req-1") == {
        "type": "https://condo-admin/errores/rfc-duplicado",
        "title": "El RFC ya está registrado",
        "status": 409,
        "code": "RFC_DUPLICADO",
        "detail": "detalle",
        "requestId": "req-1",
    }


def test_problem_omits_optional_fields() -> None:
    assert forbidden().to_problem() == {
        "type": "https://condo-admin/errores/prohibido",
        "title": "No tienes permiso para realizar esta operación",
        "status": 403,
        "code": "PROHIBIDO",
    }


def test_to_response_uses_problem_content_type() -> None:
    response = not_authenticated().to_response("req-2")
    assert response["statusCode"] == 401
    assert response["headers"] == {"Content-Type": PROBLEM_CONTENT_TYPE}
    assert json.loads(response["body"])["requestId"] == "req-2"


def test_field_errors_are_serialized() -> None:
    error = DomainError(
        400, "VALIDACION", "Datos inválidos",
        errores=[FieldError("fiscal.rfc", "RFC_FORMATO_INVALIDO", "Formato inválido")],
    )
    assert error.to_problem()["errores"] == [
        {"campo": "fiscal.rfc", "code": "RFC_FORMATO_INVALIDO", "mensaje": "Formato inválido"}
    ]


def test_validation_error_maps_to_400_validacion() -> None:
    error = from_validation_error(_validation_error({"edad": "x"}))
    assert (error.status, error.code) == (400, "VALIDACION")
    campos = {(e.campo, e.code) for e in error.errores}
    assert campos == {("nombre", "REQUERIDO"), ("edad", "INT_PARSING")}


def test_extra_field_maps_to_campo_no_permitido() -> None:
    error = from_validation_error(_validation_error({"nombre": "a", "edad": 1, "rol": "x"}))
    assert (error.status, error.code) == (400, "CAMPO_NO_PERMITIDO")
    assert error.errores[0].campo == "rol"
