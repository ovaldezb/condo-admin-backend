"""Errores de dominio y su conversión a respuestas ``application/problem+json`` (RFC 9457)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

PROBLEM_CONTENT_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://condo-admin/errores/"

_ERROR_CODES = {
    "missing": "REQUERIDO",
    "extra_forbidden": "CAMPO_NO_PERMITIDO",
}


@dataclass(frozen=True)
class FieldError:
    campo: str
    code: str
    mensaje: str

    def as_dict(self) -> dict[str, str]:
        return {"campo": self.campo, "code": self.code, "mensaje": self.mensaje}


@dataclass
class DomainError(Exception):
    """Error esperado del negocio, con un ``code`` estable que consumen los clientes."""

    status: int
    code: str
    title: str
    detail: str | None = None
    errores: list[FieldError] = field(default_factory=list)

    def __post_init__(self) -> None:
        super().__init__(f"{self.status} {self.code}")

    def to_problem(self, request_id: str | None = None) -> dict[str, Any]:
        problem: dict[str, Any] = {
            "type": PROBLEM_TYPE_BASE + self.code.lower().replace("_", "-"),
            "title": self.title,
            "status": self.status,
            "code": self.code,
        }
        if self.detail:
            problem["detail"] = self.detail
        if request_id:
            problem["requestId"] = request_id
        if self.errores:
            problem["errores"] = [error.as_dict() for error in self.errores]
        return problem

    def to_response(self, request_id: str | None = None) -> dict[str, Any]:
        """Respuesta en el formato de proxy de API Gateway HTTP API (payload 2.0)."""
        return {
            "statusCode": self.status,
            "headers": {"Content-Type": PROBLEM_CONTENT_TYPE},
            "body": json.dumps(self.to_problem(request_id), ensure_ascii=False),
        }


def not_authenticated() -> DomainError:
    return DomainError(401, "NO_AUTENTICADO", "Se requiere una sesión válida")


def forbidden() -> DomainError:
    return DomainError(403, "PROHIBIDO", "No tienes permiso para realizar esta operación")


def from_validation_error(exc: ValidationError) -> DomainError:
    """Convierte errores de Pydantic en 400 ``VALIDACION`` o ``CAMPO_NO_PERMITIDO``."""
    errores = [
        FieldError(
            campo=".".join(str(part) for part in error["loc"]),
            code=_ERROR_CODES.get(error["type"], error["type"].upper()),
            mensaje=error["msg"],
        )
        for error in exc.errors()
    ]
    if any(error["type"] == "extra_forbidden" for error in exc.errors()):
        return DomainError(400, "CAMPO_NO_PERMITIDO", "La petición incluye campos no permitidos",
                           errores=errores)
    return DomainError(400, "VALIDACION", "La petición tiene datos inválidos", errores=errores)
