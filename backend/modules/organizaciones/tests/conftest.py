"""Fixtures del módulo organizaciones: MongoDB real, Cognito y S3 simulados con moto."""

from __future__ import annotations

import copy
import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws
from testcontainers.community.mongodb import MongoDbContainer

from condo_core.mongo import PLATFORM_DB, SHARED_DB, get_client, reset_client
from condo_core.testing import FakeLambdaContext, claims_for, http_event
from seed_catalogos import seed

REGION = "us-east-1"
LOGOS_BUCKET = "condo-logos-test"

Resultado = tuple[int, dict[str, str], Any]
Invoke = Callable[[dict[str, Any]], Resultado]

ALTA_VALIDA: dict[str, Any] = {
    "nombreComercial": "Administradora del Bajío",
    "contacto": {"nombre": "Laura Pérez", "correo": "laura@example.com", "telefono": "4421234567"},
    "fiscal": {
        "rfc": "ABC010101AB1",
        "razonSocial": "Administradora del Bajío SA de CV",
        "regimenFiscal": "601",
        "codigoPostal": "76000",
    },
    "modulosHabilitados": ["condominios", "cuotas"],
    "facturacion": {"diaCorte": 1, "diaLimitePago": 10},
    "adminInicial": {"nombre": "Carlos Ruiz", "correo": "carlos@example.com"},
}


@pytest.fixture(scope="session")
def mongo_uri() -> Iterator[str]:
    with MongoDbContainer("mongo:8") as container:
        yield container.get_connection_url()


@pytest.fixture
def mongo(mongo_uri: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Bases ``platform`` y ``shared`` limpias, con catálogos e índices sembrados."""
    monkeypatch.setenv("MONGODB_URI", mongo_uri)
    reset_client()
    client = get_client()
    for name in client.list_database_names():
        if name in (PLATFORM_DB, SHARED_DB) or name.startswith("t_"):
            client.drop_database(name)
    seed(client)
    yield
    reset_client()


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    """User pool con los grupos y ``custom:tenant_id``, y bucket de logotipos, simulados."""
    from organizaciones import identity, logos

    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(name, value)

    with mock_aws():
        identity.reset_clients()
        logos.reset_clients()
        cognito = boto3.client("cognito-idp", region_name=REGION)
        pool_id = cognito.create_user_pool(
            PoolName="condo-test",
            UsernameAttributes=["email"],
            Schema=[
                {
                    "Name": "tenant_id",
                    "AttributeDataType": "String",
                    "Mutable": False,
                    "StringAttributeConstraints": {"MinLength": "32", "MaxLength": "32"},
                }
            ],
        )["UserPool"]["Id"]
        for group in ("SUPER_ADMIN", "ADMIN", "ASISTENTE"):
            cognito.create_group(UserPoolId=pool_id, GroupName=group)

        boto3.client("s3", region_name=REGION).create_bucket(Bucket=LOGOS_BUCKET)

        monkeypatch.setenv("USER_POOL_ID", pool_id)
        monkeypatch.setenv("LOGOS_BUCKET", LOGOS_BUCKET)
        yield {"user_pool_id": pool_id, "logos_bucket": LOGOS_BUCKET}
        identity.reset_clients()
        logos.reset_clients()


@pytest.fixture
def invoke() -> Invoke:
    """Invoca la Lambda y devuelve ``(status, headers, cuerpo JSON)``."""
    from organizaciones.handler import lambda_handler

    def _invoke(event: dict[str, Any]) -> Resultado:
        response = lambda_handler(event, FakeLambdaContext())
        body = response.get("body")
        return (
            response["statusCode"],
            response.get("headers") or {},
            json.loads(body) if body else None,
        )

    return _invoke


@pytest.fixture
def alta() -> Callable[..., dict[str, Any]]:
    """Cuerpo de alta válido; los argumentos reemplazan secciones de primer nivel."""

    def _alta(**overrides: Any) -> dict[str, Any]:
        body = copy.deepcopy(ALTA_VALIDA)
        body.update(overrides)
        return body

    return _alta


@pytest.fixture
def super_admin(invoke: Invoke) -> Callable[..., Resultado]:
    """Invoca una ruta con un token de SUPER_ADMIN."""

    def _call(method: str, path: str, body: Any = None,
              headers: dict[str, str] | None = None) -> Resultado:
        return invoke(http_event(claims_for("SUPER_ADMIN"), method=method, path=path,
                                 body=body, headers=headers))

    return _call


@pytest.fixture
def crear(super_admin: Callable[..., Resultado]) -> Callable[..., Resultado]:
    """``POST /organizaciones`` con una ``Idempotency-Key`` nueva salvo que se indique otra."""

    def _crear(body: dict[str, Any], key: str | None = None) -> Resultado:
        return super_admin("POST", "/organizaciones", body,
                           {"idempotency-key": key or str(uuid.uuid4())})

    return _crear
