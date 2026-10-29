"""Carreras y reintentos de la saga de alta, e invitación (casos límite de spec.md)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import boto3
import pytest

from condo_core.mongo import platform_db
from organizaciones import identity, provisioning, repository

pytestmark = pytest.mark.usefixtures("mongo", "aws")

Crear = Callable[..., tuple[int, dict[str, str], Any]]
Alta = Callable[..., dict[str, Any]]


def _create_user(pool_id: str, email: str, tenant_id: str | None) -> None:
    attributes = [{"Name": "email", "Value": email}]
    if tenant_id:
        attributes.append({"Name": "custom:tenant_id", "Value": tenant_id})
    boto3.client("cognito-idp").admin_create_user(UserPoolId=pool_id, Username=email,
                                                  UserAttributes=attributes)


def test_rfc_race_between_check_and_insert_is_409(crear: Crear, alta: Alta,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    crear(alta())
    monkeypatch.setattr(repository, "rfc_exists", lambda _: False)

    status, _, body = crear(alta(adminInicial={"nombre": "Otra", "correo": "otra@example.com"}))

    assert (status, body["code"]) == (409, "RFC_DUPLICADO")
    assert platform_db()["organizaciones"].count_documents({}) == 1


def test_idempotency_key_race_returns_winner(crear: Crear, alta: Alta,
                                             monkeypatch: pytest.MonkeyPatch) -> None:
    key = str(uuid.uuid4())
    _, _, first = crear(alta(), key)

    real_find = repository.find_by_idempotency_key
    calls = {"n": 0}

    def _miss_first_time(k: str) -> Any:
        calls["n"] += 1
        return None if calls["n"] == 1 else real_find(k)

    monkeypatch.setattr(repository, "find_by_idempotency_key", _miss_first_time)
    monkeypatch.setattr(repository, "rfc_exists", lambda _: False)
    monkeypatch.setattr(identity, "admin_exists", lambda _: False)

    status, _, second = crear(alta(), key)

    assert status == 201
    assert second["tenantId"] == first["tenantId"]
    assert platform_db()["organizaciones"].count_documents({}) == 1


def test_email_taken_between_check_and_creation_is_409(
    crear: Crear, alta: Alta, aws: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    otro_tenant = "e" * 32
    _create_user(aws["user_pool_id"], "carlos@example.com", otro_tenant)
    monkeypatch.setattr(identity, "admin_exists", lambda _: False)

    status, _, body = crear(alta())

    assert (status, body["code"]) == (409, "CORREO_EN_USO")
    assert platform_db()["organizaciones"].count_documents({}) == 0
    user = boto3.client("cognito-idp").admin_get_user(UserPoolId=aws["user_pool_id"],
                                                      Username="carlos@example.com")
    attributes = {a["Name"]: a["Value"] for a in user["UserAttributes"]}
    assert attributes["custom:tenant_id"] == otro_tenant


def test_create_admin_reuses_user_of_same_tenant(aws: dict[str, str]) -> None:
    tenant_id = "f" * 32
    _create_user(aws["user_pool_id"], "reintento@example.com", tenant_id)

    sub = identity.create_admin("reintento@example.com", "Reintento", tenant_id)

    assert sub
    groups = boto3.client("cognito-idp").admin_list_groups_for_user(
        UserPoolId=aws["user_pool_id"], Username="reintento@example.com")["Groups"]
    assert [g["GroupName"] for g in groups] == ["ADMIN"]


def test_delete_admin_if_tenant_ignores_missing_user() -> None:
    assert identity.delete_admin_if_tenant("nadie@example.com", "a" * 32) is False


def test_invitation_states(aws: dict[str, str]) -> None:
    pool_id = aws["user_pool_id"]
    _create_user(pool_id, "pendiente@example.com", "a" * 32)
    ahora = datetime.now(UTC)

    assert identity.invitation_state("pendiente@example.com", ahora) == "pendiente"
    assert identity.invitation_state("pendiente@example.com", None) == "pendiente"
    assert identity.invitation_state("pendiente@example.com",
                                     ahora - timedelta(days=8)) == "vencida"

    boto3.client("cognito-idp").admin_set_user_password(
        UserPoolId=pool_id, Username="pendiente@example.com",
        Password="Contrasena-Segura-123", Permanent=True)
    assert identity.invitation_state("pendiente@example.com",
                                     ahora - timedelta(days=8)) == "aceptada"


def test_insert_rejects_admin_fields_that_belong_to_activation() -> None:
    with pytest.raises(ValueError, match="se fijan al activar"):
        repository.insert_aprovisionando({"_id": "x", "adminInicial": {"sub": "s"}})


def test_reconciler_skips_failures_and_retries_later(monkeypatch: pytest.MonkeyPatch) -> None:
    platform_db()["organizaciones"].insert_one({
        "_id": "9" * 32, "estatus": "aprovisionando", "fiscal": {"rfc": "AAA010101AA1"},
        "idempotencyKey": "k", "adminInicial": {"nombre": "A", "correo": "a@example.com"},
        "creadoEn": datetime.now(UTC) - timedelta(hours=1),
    })

    def _fail(*_: Any) -> bool:
        raise RuntimeError("Cognito no disponible")

    with monkeypatch.context() as patch:
        patch.setattr(identity, "delete_admin_if_tenant", _fail)
        assert provisioning.reconcile_stale() == 0
    # El documento se conserva para que la siguiente corrida reintente la compensación.
    assert platform_db()["organizaciones"].count_documents({}) == 1

    assert provisioning.reconcile_stale() == 1
    assert platform_db()["organizaciones"].count_documents({}) == 0


def test_failed_compensation_in_request_is_left_for_reconciler(
    crear: Crear, alta: Alta, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _fail(*_: Any, **__: Any) -> Any:
        raise RuntimeError("falla inyectada")

    monkeypatch.setattr(repository, "set_activa", _fail)
    monkeypatch.setattr(identity, "delete_admin_if_tenant", _fail)

    status, _, body = crear(alta())

    assert (status, body["code"]) == (503, "ALTA_FALLIDA")
    doc = platform_db()["organizaciones"].find_one({})
    assert doc is not None and doc["estatus"] == "aprovisionando"
