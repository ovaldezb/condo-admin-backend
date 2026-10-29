"""Aislamiento entre tenants en el alta (T037, principio III y IV).

Cada ADMIN queda ligado sólo a su propia organización, y el disparador de Cognito le emite un
token con únicamente su ``tenant_id``.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import boto3
import pytest

from condo_core.testing import FakeLambdaContext

pytestmark = pytest.mark.usefixtures("mongo", "aws")

TRIGGER = Path(__file__).resolve().parents[5] / "infra/shared/src/cognito_triggers/handler.py"


def _load_trigger() -> ModuleType:
    """El disparador vive en otro proyecto de uv; se carga desde su archivo."""
    spec = importlib.util.spec_from_file_location("cognito_triggers_handler", TRIGGER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _token_claims(trigger: ModuleType, pool_id: str, email: str) -> dict[str, Any]:
    user = boto3.client("cognito-idp").admin_get_user(UserPoolId=pool_id, Username=email)
    attributes = {a["Name"]: a["Value"] for a in user["UserAttributes"]}
    event = {
        "request": {
            "userAttributes": attributes,
            "groupConfiguration": {"groupsToOverride": ["ADMIN"]},
        },
        "response": {"claimsAndScopeOverrideDetails": None},
    }
    result = trigger.handler(event, FakeLambdaContext())
    details = result["response"]["claimsAndScopeOverrideDetails"]
    return dict(details["accessTokenGeneration"]["claimsToAddOrOverride"])


def test_each_admin_gets_only_its_own_tenant(
    crear: Callable[..., Any], alta: Callable[..., dict[str, Any]], aws: dict[str, str]
) -> None:
    _, _, org_a = crear(alta(adminInicial={"nombre": "Admin A", "correo": "a@example.com"}))
    _, _, org_b = crear(alta(
        fiscal={**alta()["fiscal"], "rfc": "XYZ010101AB1"},
        adminInicial={"nombre": "Admin B", "correo": "b@example.com"},
    ))
    tenant_a, tenant_b = org_a["tenantId"], org_b["tenantId"]
    assert tenant_a != tenant_b

    trigger = _load_trigger()
    assert _token_claims(trigger, aws["user_pool_id"], "a@example.com") == {"tenant_id": tenant_a}
    assert _token_claims(trigger, aws["user_pool_id"], "b@example.com") == {"tenant_id": tenant_b}
