"""Reconciliador de altas atascadas en ``aprovisionando`` (T040, SC-006)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import boto3
import pytest

from condo_core.mongo import platform_db
from condo_core.testing import FakeLambdaContext
from organizaciones.handler import lambda_handler

pytestmark = pytest.mark.usefixtures("mongo", "aws")

SCHEDULED_EVENT = {"source": "aws.events", "detail-type": "Scheduled Event"}


def _insert(tenant_id: str, estatus: str, minutes_ago: int, email: str) -> None:
    platform_db()["organizaciones"].insert_one({
        "_id": tenant_id,
        "estatus": estatus,
        "fiscal": {"rfc": f"RFC{tenant_id[:9].upper()}"},
        "idempotencyKey": f"key-{tenant_id}",
        "adminInicial": {"nombre": "Admin", "correo": email},
        "creadoEn": datetime.now(UTC) - timedelta(minutes=minutes_ago),
    })


def _create_user(pool_id: str, email: str, tenant_id: str) -> None:
    boto3.client("cognito-idp").admin_create_user(
        UserPoolId=pool_id, Username=email,
        UserAttributes=[{"Name": "email", "Value": email},
                        {"Name": "custom:tenant_id", "Value": tenant_id}],
    )


def _users(pool_id: str) -> set[str]:
    users = boto3.client("cognito-idp").list_users(UserPoolId=pool_id)["Users"]
    return {next(a["Value"] for a in u["Attributes"] if a["Name"] == "email") for u in users}


def test_stale_provisioning_is_compensated(aws: dict[str, str]) -> None:
    pool_id = aws["user_pool_id"]
    stale, recent, active = "1" * 32, "2" * 32, "3" * 32
    _insert(stale, "aprovisionando", 20, "atascada@example.com")
    _create_user(pool_id, "atascada@example.com", stale)
    _insert(recent, "aprovisionando", 5, "reciente@example.com")
    _create_user(pool_id, "reciente@example.com", recent)
    _insert(active, "activa", 60, "activa@example.com")
    _create_user(pool_id, "activa@example.com", active)

    assert lambda_handler(SCHEDULED_EVENT, FakeLambdaContext()) == {"reconciliadas": 1}

    restantes = {d["_id"] for d in platform_db()["organizaciones"].find({}, {"_id": 1})}
    assert restantes == {recent, active}
    assert _users(pool_id) == {"reciente@example.com", "activa@example.com"}


def test_user_of_another_tenant_is_never_deleted(aws: dict[str, str]) -> None:
    pool_id = aws["user_pool_id"]
    stale = "4" * 32
    _insert(stale, "aprovisionando", 30, "compartido@example.com")
    _create_user(pool_id, "compartido@example.com", "5" * 32)

    assert lambda_handler(SCHEDULED_EVENT, FakeLambdaContext()) == {"reconciliadas": 1}

    assert platform_db()["organizaciones"].count_documents({}) == 0
    assert _users(pool_id) == {"compartido@example.com"}


def test_nothing_to_reconcile() -> None:
    assert lambda_handler(SCHEDULED_EVENT, FakeLambdaContext()) == {"reconciliadas": 0}
