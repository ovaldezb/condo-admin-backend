"""Alta de organizaciones: saga atómica e idempotente (T036, FR-003 a FR-017)."""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from typing import Any

import boto3
import pytest

from condo_core.mongo import get_client, platform_db, shared_db
from organizaciones import identity, repository

pytestmark = pytest.mark.usefixtures("mongo", "aws")

Crear = Callable[..., tuple[int, dict[str, str], Any]]
Alta = Callable[..., dict[str, Any]]


def _cognito_users(pool_id: str) -> list[dict[str, Any]]:
    return boto3.client("cognito-idp").list_users(UserPoolId=pool_id)["Users"]


def _attributes(user: dict[str, Any]) -> dict[str, str]:
    return {a["Name"]: a["Value"] for a in user.get("Attributes", user.get("UserAttributes", []))}


def test_successful_alta(crear: Crear, alta: Alta, aws: dict[str, str]) -> None:
    status, headers, body = crear(alta())

    assert status == 201
    tenant_id = body["tenantId"]
    assert re.fullmatch(r"[0-9a-f]{32}", tenant_id)
    assert body["estatus"] == "activa"
    assert body["version"] == 1
    assert headers["ETag"] == '"1"'
    assert headers["Location"] == f"/organizaciones/{tenant_id}"
    assert body["adminInicial"]["invitacion"] == "pendiente"
    assert body["fiscal"]["rfc"] == "ABC010101AB1"

    doc = platform_db()["organizaciones"].find_one({"_id": tenant_id})
    assert doc is not None
    assert doc["adminInicial"]["sub"]
    assert doc["adminInicial"]["invitacionEnviadaEn"] is not None
    assert doc["busqueda"] == (
        "administradora del bajio administradora del bajio sa de cv abc010101ab1"
    )

    cognito = boto3.client("cognito-idp")
    user = cognito.admin_get_user(UserPoolId=aws["user_pool_id"], Username="carlos@example.com")
    assert _attributes(user)["custom:tenant_id"] == tenant_id
    groups = cognito.admin_list_groups_for_user(UserPoolId=aws["user_pool_id"],
                                                Username="carlos@example.com")["Groups"]
    assert [g["GroupName"] for g in groups] == ["ADMIN"]

    assert f"t_{tenant_id}" not in get_client().list_database_names()


def test_rfc_and_emails_are_normalized(crear: Crear, alta: Alta) -> None:
    body = alta(
        fiscal={**alta()["fiscal"], "rfc": " abc010101ab1 "},
        adminInicial={"nombre": "Carlos Ruiz", "correo": "Carlos@Example.COM"},
    )
    status, _, created = crear(body)
    assert status == 201
    assert created["fiscal"]["rfc"] == "ABC010101AB1"
    assert created["adminInicial"]["correo"] == "carlos@example.com"


def test_duplicate_rfc_even_if_disabled_is_409(crear: Crear, alta: Alta) -> None:
    _, _, first = crear(alta())
    platform_db()["organizaciones"].update_one({"_id": first["tenantId"]},
                                               {"$set": {"estatus": "deshabilitada"}})
    status, _, body = crear(alta(adminInicial={"nombre": "Otra", "correo": "otra@example.com"}))
    assert (status, body["code"]) == (409, "RFC_DUPLICADO")


def test_existing_admin_email_is_409(crear: Crear, alta: Alta, aws: dict[str, str]) -> None:
    boto3.client("cognito-idp").admin_create_user(UserPoolId=aws["user_pool_id"],
                                                  Username="carlos@example.com")
    status, _, body = crear(alta())
    assert (status, body["code"]) == (409, "CORREO_EN_USO")
    assert platform_db()["organizaciones"].count_documents({}) == 0


def _fail(*_: Any, **__: Any) -> Any:
    raise RuntimeError("falla inyectada")


def _assert_nothing_left(status: int, body: Any, pool_id: str) -> None:
    assert (status, body["code"]) == (503, "ALTA_FALLIDA")
    assert platform_db()["organizaciones"].count_documents({}) == 0
    assert _cognito_users(pool_id) == []


@pytest.mark.parametrize(
    ("target", "attribute"),
    [
        (repository, "insert_aprovisionando"),
        (identity, "create_admin"),
        (repository, "set_activa"),
    ],
    ids=["paso-1-registro", "paso-2-admin", "paso-3-activacion"],
)
def test_failure_in_any_step_leaves_nothing(
    crear: Crear, alta: Alta, aws: dict[str, str], monkeypatch: pytest.MonkeyPatch,
    target: Any, attribute: str,
) -> None:
    monkeypatch.setattr(target, attribute, _fail)
    status, _, body = crear(alta())
    _assert_nothing_left(status, body, aws["user_pool_id"])


def test_failure_after_user_creation_removes_user(
    crear: Crear, alta: Alta, aws: dict[str, str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    """El usuario se creó en Cognito, pero el paso 2 falló antes de terminar."""
    original = identity.create_admin

    def _create_then_fail(email: str, nombre: str, tenant_id: str) -> str:
        original(email, nombre, tenant_id)
        raise RuntimeError("falla inyectada después de crear el usuario")

    monkeypatch.setattr(identity, "create_admin", _create_then_fail)
    status, _, body = crear(alta())
    _assert_nothing_left(status, body, aws["user_pool_id"])


def test_same_key_and_body_returns_same_organization(crear: Crear, alta: Alta) -> None:
    key = str(uuid.uuid4())
    first_status, _, first = crear(alta(), key)
    second_status, headers, second = crear(alta(), key)

    assert (first_status, second_status) == (201, 201)
    assert second["tenantId"] == first["tenantId"]
    assert headers["ETag"] == '"1"'
    assert platform_db()["organizaciones"].count_documents({}) == 1


def test_same_key_with_different_body_is_422(crear: Crear, alta: Alta) -> None:
    key = str(uuid.uuid4())
    crear(alta(), key)
    status, _, body = crear(alta(nombreComercial="Otro nombre"), key)
    assert (status, body["code"]) == (422, "IDEMPOTENCY_KEY_REUTILIZADA")


def test_same_key_while_provisioning_is_409(crear: Crear, alta: Alta) -> None:
    key = str(uuid.uuid4())
    crear(alta(), key)
    platform_db()["organizaciones"].update_one({"idempotencyKey": key},
                                               {"$set": {"estatus": "aprovisionando"}})
    status, _, body = crear(alta(), key)
    assert (status, body["code"]) == (409, "ALTA_EN_PROCESO")


def test_missing_idempotency_key_is_428(super_admin: Callable[..., Any], alta: Alta) -> None:
    status, _, body = super_admin("POST", "/organizaciones", alta())
    assert (status, body["code"]) == (428, "IDEMPOTENCY_KEY_REQUERIDA")


def test_invalid_idempotency_key_is_400(crear: Crear, alta: Alta) -> None:
    status, _, body = crear(alta(), "no-es-uuid")
    assert (status, body["code"]) == (400, "VALIDACION")
    assert body["errores"][0]["campo"] == "Idempotency-Key"


def test_unknown_field_is_400_campo_no_permitido(crear: Crear, alta: Alta) -> None:
    status, _, body = crear(alta(tenantId="a" * 32))
    assert (status, body["code"]) == (400, "CAMPO_NO_PERMITIDO")


@pytest.mark.parametrize(
    ("overrides", "campo"),
    [
        ({"modulosHabilitados": []}, "modulosHabilitados"),
        ({"modulosHabilitados": ["cuotas", "cuotas"]}, "modulosHabilitados"),
        ({"modulosHabilitados": ["no-existe"]}, "modulosHabilitados"),
        ({"facturacion": {"diaCorte": 29, "diaLimitePago": 10}}, "facturacion.diaCorte"),
        ({"contacto": {"nombre": "L", "correo": "laura@example.com", "telefono": "4421234567"}},
         "contacto.nombre"),
        ({"contacto": {"nombre": "Laura", "correo": "no-es-correo", "telefono": "4421234567"}},
         "contacto.correo"),
        ({"contacto": {"nombre": "Laura", "correo": "laura@example.com", "telefono": "123"}},
         "contacto.telefono"),
    ],
)
def test_invalid_data_is_400(crear: Crear, alta: Alta, overrides: dict[str, Any],
                             campo: str) -> None:
    status, _, body = crear(alta(**overrides))
    assert (status, body["code"]) == (400, "VALIDACION")
    assert campo in [e["campo"] for e in body["errores"]]


def test_unavailable_module_is_400(crear: Crear, alta: Alta) -> None:
    shared_db()["modulos"].update_one({"_id": "pagos"}, {"$set": {"disponible": False}})
    status, _, body = crear(alta(modulosHabilitados=["pagos"]))
    assert (status, body["code"]) == (400, "VALIDACION")
    assert body["errores"][0] == {"campo": "modulosHabilitados", "code": "MODULO_NO_DISPONIBLE",
                                  "mensaje": "Módulo no disponible: pagos"}


@pytest.mark.parametrize(
    ("rfc", "regimen", "code"),
    [
        ("ABC010101AB1", "605", "REGIMEN_NO_APLICA"),
        ("GODE561231GR8", "601", "REGIMEN_NO_APLICA"),
        ("ABC010101AB1", "999", "REGIMEN_INEXISTENTE"),
    ],
)
def test_regimen_must_apply_to_person_type(crear: Crear, alta: Alta, rfc: str, regimen: str,
                                           code: str) -> None:
    fiscal = {**alta()["fiscal"], "rfc": rfc, "regimenFiscal": regimen}
    status, _, body = crear(alta(fiscal=fiscal))
    assert (status, body["code"]) == (400, "VALIDACION")
    assert body["errores"] == [{"campo": "fiscal.regimenFiscal", "code": code,
                                "mensaje": body["errores"][0]["mensaje"]}]


def test_optional_address_is_validated_and_canonicalized(crear: Crear, alta: Alta) -> None:
    direccion = {"calle": "Av. Constituyentes", "numeroExterior": "100", "colonia": "Centro",
                 "municipio": "Querétaro", "estado": "queretaro", "codigoPostal": "76000"}
    status, _, body = crear(alta(direccion=direccion))
    assert status == 201
    assert body["direccion"]["estado"] == "Querétaro"

    status, _, body = crear(alta(fiscal={**alta()["fiscal"], "rfc": "XYZ010101AB1"},
                                 adminInicial={"nombre": "Ana", "correo": "ana@example.com"},
                                 direccion={**direccion, "estado": "Texas"}))
    assert (status, body["code"]) == (400, "VALIDACION")
    assert body["errores"][0]["code"] == "ESTADO_INVALIDO"
