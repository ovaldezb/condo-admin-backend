"""Disparador Pre Token Generation V2 de Cognito (contracts/cognito-claims.md).

Corre en cada inicio de sesión y en cada renovación con refresh token:

1. SUPER_ADMIN → el evento sale sin cambios.
2. ADMIN o ASISTENTE → se exige ``custom:tenant_id`` y que la organización esté ``activa``.
   Si no, se lanza una excepción y Cognito niega el token.
3. Se agrega el claim ``tenant_id`` al access token.

Sólo se registran ``tenant_id`` y el resultado; nunca el correo ni otros atributos.
"""

from __future__ import annotations

from typing import Any

from condo_core.auth import SUPER_ADMIN, TENANT_ID_PATTERN
from condo_core.logging import inject_lambda_context, logger
from condo_core.mongo import platform_db

ESTATUS_ACTIVA = "activa"


class TokenDenegado(Exception):  # noqa: N818 - el nombre describe la decisión de negocio
    """Cognito convierte esta excepción en un rechazo de la emisión del token."""


@inject_lambda_context()
def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    request = event.get("request", {})
    groups = request.get("groupConfiguration", {}).get("groupsToOverride") or []
    if SUPER_ADMIN in groups:
        logger.info("token_super_admin")
        return event

    tenant_id = request.get("userAttributes", {}).get("custom:tenant_id", "")
    if not TENANT_ID_PATTERN.fullmatch(tenant_id):
        logger.warning("token_denegado", extra={"motivo": "TENANT_NO_ASIGNADO"})
        raise TokenDenegado("TENANT_NO_ASIGNADO")

    logger.append_keys(tenant_id=tenant_id)
    organizacion = platform_db()["organizaciones"].find_one({"_id": tenant_id}, {"estatus": 1})
    if organizacion is None or organizacion.get("estatus") != ESTATUS_ACTIVA:
        logger.warning("token_denegado", extra={"motivo": "ORGANIZACION_DESHABILITADA"})
        raise TokenDenegado("ORGANIZACION_DESHABILITADA")

    response = event.setdefault("response", {})
    response["claimsAndScopeOverrideDetails"] = {
        "accessTokenGeneration": {"claimsToAddOrOverride": {"tenant_id": tenant_id}},
    }
    logger.info("token_emitido")
    return event
