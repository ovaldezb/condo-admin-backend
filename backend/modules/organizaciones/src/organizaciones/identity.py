"""Operaciones de Cognito sobre el primer ADMIN de cada organización (research.md, decisión 10).

Nunca se registran correos ni otros atributos en los logs (principio VI).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

import boto3

from condo_core.auth import ADMIN
from condo_core.errors import DomainError

INVITACION_VIGENCIA = timedelta(days=7)
CONFIRMED = "CONFIRMED"
FORCE_CHANGE_PASSWORD = "FORCE_CHANGE_PASSWORD"  # noqa: S105 - estatus de Cognito


@lru_cache(maxsize=1)
def _cognito() -> Any:
    return boto3.client("cognito-idp")


def reset_clients() -> None:
    """Descarta el cliente del contenedor. Sólo para pruebas."""
    _cognito.cache_clear()


def _pool_id() -> str:
    return os.environ["USER_POOL_ID"]


def correo_en_uso() -> DomainError:
    return DomainError(409, "CORREO_EN_USO", "El correo del ADMIN ya pertenece a otro usuario")


def _attributes(user: dict[str, Any]) -> dict[str, str]:
    raw = user.get("UserAttributes") or user.get("Attributes") or []
    return {a["Name"]: a["Value"] for a in raw}


def _get_user(email: str) -> dict[str, Any] | None:
    cognito = _cognito()
    try:
        user: dict[str, Any] = cognito.admin_get_user(UserPoolId=_pool_id(), Username=email)
    except cognito.exceptions.UserNotFoundException:
        return None
    return user


def admin_exists(email: str) -> bool:
    return _get_user(email) is not None


def user_status(email: str) -> str | None:
    user = _get_user(email)
    return None if user is None else str(user["UserStatus"])


def create_admin(email: str, nombre: str, tenant_id: str) -> str:
    """Crea al primer ADMIN con su ``custom:tenant_id``, envía la invitación y lo agrega al grupo.

    Si ya existe con el mismo tenant (reintento de la saga), se reutiliza. Devuelve su ``sub``.
    """
    cognito = _cognito()
    try:
        response = cognito.admin_create_user(
            UserPoolId=_pool_id(),
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
                {"Name": "name", "Value": nombre},
                {"Name": "custom:tenant_id", "Value": tenant_id},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
        attributes = _attributes(response["User"])
    except cognito.exceptions.UsernameExistsException:
        user = _get_user(email)
        attributes = _attributes(user) if user else {}
        if attributes.get("custom:tenant_id") != tenant_id:
            raise correo_en_uso() from None

    cognito.admin_add_user_to_group(UserPoolId=_pool_id(), Username=email, GroupName=ADMIN)
    return attributes["sub"]


def delete_admin_if_tenant(email: str, tenant_id: str) -> bool:
    """Compensación: borra al usuario sólo si pertenece a ``tenant_id``.

    Nunca borra a un usuario de otra organización, aunque comparta el correo.
    """
    user = _get_user(email)
    if user is None or _attributes(user).get("custom:tenant_id") != tenant_id:
        return False
    _cognito().admin_delete_user(UserPoolId=_pool_id(), Username=email)
    return True


def resend_invitation(email: str) -> None:
    _cognito().admin_create_user(UserPoolId=_pool_id(), Username=email, MessageAction="RESEND",
                                 DesiredDeliveryMediums=["EMAIL"])


def invitation_state(email: str, enviada_en: datetime | None) -> str:
    """``aceptada``, ``vencida`` (más de 7 días sin activar) o ``pendiente``."""
    status = user_status(email)
    if status == CONFIRMED:
        return "aceptada"
    if (status == FORCE_CHANGE_PASSWORD and enviada_en is not None
            and datetime.now(UTC) - enviada_en > INVITACION_VIGENCIA):
        return "vencida"
    return "pendiente"
