"""Fixtures del módulo organizaciones: MongoDB real, Cognito y S3 simulados con moto."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import boto3
import pytest
from moto import mock_aws
from testcontainers.community.mongodb import MongoDbContainer

from condo_core.mongo import PLATFORM_DB, SHARED_DB, get_client, reset_client
from condo_core.testing import FakeLambdaContext
from seed_catalogos import seed

REGION = "us-east-1"
LOGOS_BUCKET = "condo-logos-test"


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
    client.drop_database(PLATFORM_DB)
    client.drop_database(SHARED_DB)
    seed(client)
    yield
    reset_client()


@pytest.fixture
def aws(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, str]]:
    """User pool con los grupos y ``custom:tenant_id``, y bucket de logotipos, simulados."""
    for name, value in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_SESSION_TOKEN": "testing",
        "AWS_DEFAULT_REGION": REGION,
    }.items():
        monkeypatch.setenv(name, value)

    with mock_aws():
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


@pytest.fixture
def invoke() -> Callable[[dict[str, Any]], tuple[int, dict[str, str], Any]]:
    """Invoca la Lambda y devuelve ``(status, headers, cuerpo JSON)``."""
    from organizaciones.handler import lambda_handler

    def _invoke(event: dict[str, Any]) -> tuple[int, dict[str, str], Any]:
        response = lambda_handler(event, FakeLambdaContext())
        body = response.get("body")
        return (
            response["statusCode"],
            response.get("headers") or {},
            json.loads(body) if body else None,
        )

    return _invoke
