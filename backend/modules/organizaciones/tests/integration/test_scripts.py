"""Scripts del pipeline: siembra de catálogos y alta de SUPER_ADMIN."""

from __future__ import annotations

import boto3
import pytest
from pymongo.errors import DuplicateKeyError

import crear_super_admin as csa
from condo_core.mongo import get_client, platform_db, shared_db
from seed_catalogos import MODULOS, REGIMENES_FISCALES, seed


@pytest.mark.usefixtures("mongo")
def test_seed_is_idempotent_and_complete() -> None:
    assert seed(get_client()) == {"modulos": 6, "regimenes_fiscales": 19}
    assert shared_db()["modulos"].count_documents({"disponible": True}) == len(MODULOS)
    assert shared_db()["regimenes_fiscales"].count_documents({}) == len(REGIMENES_FISCALES)

    regimen_601 = shared_db()["regimenes_fiscales"].find_one({"_id": "601"})
    assert regimen_601 is not None
    assert (regimen_601["personaMoral"], regimen_601["personaFisica"]) == (True, False)


@pytest.mark.usefixtures("mongo")
def test_seed_creates_platform_indexes() -> None:
    indexes = platform_db()["organizaciones"].index_information()
    assert indexes["rfc_unico"]["unique"] is True
    assert indexes["idempotency_key_unica"]["unique"] is True
    assert indexes["estatus_creado"]["key"] == [("estatus", 1), ("creadoEn", -1)]

    organizaciones = platform_db()["organizaciones"]
    organizaciones.insert_one({"_id": "1", "fiscal": {"rfc": "ABC010101AB1"},
                               "idempotencyKey": "k1"})
    with pytest.raises(DuplicateKeyError):
        organizaciones.insert_one({"_id": "2", "fiscal": {"rfc": "ABC010101AB1"},
                                   "idempotencyKey": "k2"})


def _groups(pool_id: str, email: str) -> list[str]:
    cognito = boto3.client("cognito-idp")
    groups = cognito.admin_list_groups_for_user(UserPoolId=pool_id, Username=email)["Groups"]
    return [g["GroupName"] for g in groups]


def test_crear_super_admin_creates_then_is_idempotent(aws: dict[str, str]) -> None:
    pool_id = aws["user_pool_id"]
    cognito = boto3.client("cognito-idp")
    assert csa.crear_super_admin(cognito, pool_id, " Admin@Example.com ") == "creado"
    assert csa.crear_super_admin(cognito, pool_id, "admin@example.com") == "existente"
    assert _groups(pool_id, "admin@example.com") == ["SUPER_ADMIN"]


def test_crear_super_admin_refuses_tenant_user(aws: dict[str, str]) -> None:
    pool_id = aws["user_pool_id"]
    cognito = boto3.client("cognito-idp")
    cognito.admin_create_user(
        UserPoolId=pool_id,
        Username="admin.org@example.com",
        UserAttributes=[{"Name": "email", "Value": "admin.org@example.com"},
                        {"Name": "custom:tenant_id", "Value": "a" * 32}],
    )
    with pytest.raises(csa.SuperAdminError):
        csa.crear_super_admin(cognito, pool_id, "admin.org@example.com")


def test_crear_super_admin_rejects_invalid_email(aws: dict[str, str]) -> None:
    with pytest.raises(csa.SuperAdminError):
        csa.crear_super_admin(boto3.client("cognito-idp"), aws["user_pool_id"], "no-es-correo")


def test_main_uses_env_pool_and_hides_email(
    aws: dict[str, str], capsys: pytest.CaptureFixture[str]
) -> None:
    assert csa.main(["--email", "nuevo@example.com"]) == 0
    output = capsys.readouterr()
    assert "SUPER_ADMIN creado" in output.out
    assert "nuevo@example.com" not in output.out + output.err

    assert csa.main(["--email", "invalido"]) == 1


def test_main_requires_pool_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("USER_POOL_ID", raising=False)
    with pytest.raises(SystemExit):
        csa.main(["--email", "x@example.com"])
