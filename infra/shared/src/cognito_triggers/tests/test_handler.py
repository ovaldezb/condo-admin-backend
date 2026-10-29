from __future__ import annotations

import io

import pytest

from cognito_triggers.handler import TokenDenegado, handler
from condo_core.mongo import platform_db
from condo_core.testing import TENANT_A, FakeLambdaContext

from .conftest import token_event

pytestmark = pytest.mark.usefixtures("mongo")


def _insert(tenant_id: str, estatus: str) -> None:
    platform_db()["organizaciones"].insert_one({"_id": tenant_id, "estatus": estatus})


def test_super_admin_event_is_unchanged() -> None:
    event = token_event(["SUPER_ADMIN"], {})
    result = handler(event, FakeLambdaContext())
    assert result["response"]["claimsAndScopeOverrideDetails"] is None


def test_active_organization_gets_tenant_claim() -> None:
    _insert(TENANT_A, "activa")
    event = token_event(["ADMIN"], {"custom:tenant_id": TENANT_A})
    result = handler(event, FakeLambdaContext())
    assert result["response"]["claimsAndScopeOverrideDetails"] == {
        "accessTokenGeneration": {"claimsToAddOrOverride": {"tenant_id": TENANT_A}},
    }


@pytest.mark.parametrize("estatus", ["deshabilitada", "aprovisionando"])
def test_inactive_organization_is_denied(estatus: str) -> None:
    _insert(TENANT_A, estatus)
    event = token_event(["ASISTENTE"], {"custom:tenant_id": TENANT_A})
    with pytest.raises(TokenDenegado, match="ORGANIZACION_DESHABILITADA"):
        handler(event, FakeLambdaContext())


def test_missing_organization_is_denied() -> None:
    event = token_event(["ADMIN"], {"custom:tenant_id": TENANT_A})
    with pytest.raises(TokenDenegado, match="ORGANIZACION_DESHABILITADA"):
        handler(event, FakeLambdaContext())


@pytest.mark.parametrize("attributes", [{}, {"custom:tenant_id": "no-es-un-tenant"}])
def test_missing_or_invalid_tenant_attribute_is_denied(attributes: dict[str, str]) -> None:
    with pytest.raises(TokenDenegado, match="TENANT_NO_ASIGNADO"):
        handler(token_event(["ADMIN"], attributes), FakeLambdaContext())


def test_logs_never_include_email(logs: io.StringIO) -> None:
    _insert(TENANT_A, "activa")
    handler(token_event(["ADMIN"], {"custom:tenant_id": TENANT_A}), FakeLambdaContext())
    output = logs.getvalue()
    assert "persona@example.com" not in output
    assert TENANT_A in output
