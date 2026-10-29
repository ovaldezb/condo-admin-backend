"""Reenvío de la invitación del primer ADMIN (T039, FR-026)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest

from condo_core.mongo import platform_db

pytestmark = pytest.mark.usefixtures("mongo", "aws")

Call = Callable[..., tuple[int, dict[str, str], Any]]


@pytest.fixture
def tenant_id(crear: Call, alta: Callable[..., dict[str, Any]]) -> str:
    _, _, body = crear(alta())
    return str(body["tenantId"])


def _reenviar(super_admin: Call, tenant_id: str) -> tuple[int, dict[str, str], Any]:
    return super_admin("POST", f"/organizaciones/{tenant_id}/admin-inicial/reenviar-invitacion")


def test_pending_invitation_is_resent_without_changing_version(super_admin: Call,
                                                               tenant_id: str) -> None:
    organizaciones = platform_db()["organizaciones"]
    antes = datetime.now(UTC) - timedelta(days=3)
    organizaciones.update_one({"_id": tenant_id},
                              {"$set": {"adminInicial.invitacionEnviadaEn": antes}})

    status, _, body = _reenviar(super_admin, tenant_id)

    assert (status, body) == (204, None)
    doc = organizaciones.find_one({"_id": tenant_id})
    assert doc is not None
    assert doc["adminInicial"]["invitacionEnviadaEn"] > antes
    assert doc["version"] == 1


def test_accepted_invitation_is_409(super_admin: Call, tenant_id: str,
                                    aws: dict[str, str]) -> None:
    boto3.client("cognito-idp").admin_set_user_password(
        UserPoolId=aws["user_pool_id"], Username="carlos@example.com",
        Password="Contrasena-Segura-123", Permanent=True,
    )
    status, _, body = _reenviar(super_admin, tenant_id)
    assert (status, body["code"]) == (409, "INVITACION_YA_ACEPTADA")


def test_disabled_organization_is_409(super_admin: Call, tenant_id: str) -> None:
    platform_db()["organizaciones"].update_one({"_id": tenant_id},
                                               {"$set": {"estatus": "deshabilitada"}})
    status, _, body = _reenviar(super_admin, tenant_id)
    assert (status, body["code"]) == (409, "ORGANIZACION_DESHABILITADA")


def test_unknown_organization_is_404(super_admin: Call) -> None:
    status, _, body = _reenviar(super_admin, "d" * 32)
    assert (status, body["code"]) == (404, "NO_ENCONTRADA")
