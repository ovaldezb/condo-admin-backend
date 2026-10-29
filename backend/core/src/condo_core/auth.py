"""Lectura de claims del access token y reglas de autorización por rol.

Las reglas siguen contracts/cognito-claims.md. El autorizador JWT de la HTTP API ya validó la
firma del token; aquí se valida su contenido en cada petición (principio V).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from condo_core.errors import forbidden, not_authenticated

SUPER_ADMIN = "SUPER_ADMIN"
ADMIN = "ADMIN"
ASISTENTE = "ASISTENTE"
TENANT_ROLES = frozenset({ADMIN, ASISTENTE})
ROLES = frozenset({SUPER_ADMIN, *TENANT_ROLES})

TENANT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class Claims:
    sub: str
    username: str
    groups: tuple[str, ...]
    tenant_id: str | None

    @property
    def role(self) -> str | None:
        """El rol del usuario si tiene exactamente un grupo; si no, ``None``."""
        return self.groups[0] if len(self.groups) == 1 else None


def parse_groups(raw: Any) -> tuple[str, ...]:
    """Acepta ``cognito:groups`` como lista o como la cadena ``"[A B]"`` de la HTTP API."""
    if raw is None:
        return ()
    if isinstance(raw, str):
        inner = raw.strip()
        if inner.startswith("[") and inner.endswith("]"):
            inner = inner[1:-1]
        return tuple(part for part in re.split(r"[\s,]+", inner) if part)
    if isinstance(raw, list | tuple):
        return tuple(str(part) for part in raw)
    return ()


def claims_from_event(event: Mapping[str, Any]) -> Claims | None:
    """Extrae los claims que dejó el autorizador JWT, o ``None`` si no hay sesión."""
    raw = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims")
    )
    if not raw:
        return None
    return Claims(
        sub=str(raw.get("sub", "")),
        username=str(raw.get("username", "")),
        groups=parse_groups(raw.get("cognito:groups")),
        tenant_id=raw.get("tenant_id") or None,
    )


def require_role(claims: Claims | None, *roles: str) -> Claims:
    """Exige sesión, un único grupo permitido y un ``tenant_id`` coherente con el rol.

    Lanza ``DomainError`` 401 ``NO_AUTENTICADO`` o 403 ``PROHIBIDO``.
    """
    if claims is None:
        raise not_authenticated()
    role = claims.role
    if role is None or role not in ROLES or role not in roles:
        raise forbidden()
    if role == SUPER_ADMIN and claims.tenant_id is not None:
        raise forbidden()
    if role in TENANT_ROLES and not TENANT_ID_PATTERN.fullmatch(claims.tenant_id or ""):
        raise forbidden()
    return claims
