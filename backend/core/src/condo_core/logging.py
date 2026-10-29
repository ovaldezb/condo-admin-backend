"""Logs estructurados con identificador de tenant y de petición (principio VIII).

Nunca se registran cuerpos de petición ni de respuesta, ni el evento completo, porque pueden
contener datos personales (principio VI).
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from aws_lambda_powertools import Logger

from condo_core.auth import SUPER_ADMIN, Claims

PLATFORM_TENANT = "platform"
UNKNOWN_TENANT = "desconocido"

logger = Logger(service=os.environ.get("POWERTOOLS_SERVICE_NAME", "condo-admin"))


def inject_lambda_context() -> Callable[..., Any]:
    """Decorador para handlers: agrega el contexto de Lambda sin registrar el evento.

    ``clear_state`` evita que las llaves de una invocación (por ejemplo, ``tenant_id``) se
    filtren a la siguiente en el mismo contenedor.
    """
    return logger.inject_lambda_context(log_event=False, clear_state=True)


def tenant_for_logs(claims: Claims | None) -> str:
    if claims is None:
        return UNKNOWN_TENANT
    if claims.role == SUPER_ADMIN:
        return PLATFORM_TENANT
    return claims.tenant_id or UNKNOWN_TENANT


def bind_request(
    event: Mapping[str, Any],
    claims: Claims | None,
    target_tenant_id: str | None = None,
    lambda_request_id: str | None = None,
) -> None:
    """Agrega a todas las líneas siguientes los identificadores de tenant y de petición."""
    keys: dict[str, Any] = {
        "tenant_id": tenant_for_logs(claims),
        "request_id": event.get("requestContext", {}).get("requestId"),
    }
    if target_tenant_id is not None:
        keys["target_tenant_id"] = target_tenant_id
    if lambda_request_id is not None:
        keys["lambda_request_id"] = lambda_request_id
    logger.append_keys(**keys)
