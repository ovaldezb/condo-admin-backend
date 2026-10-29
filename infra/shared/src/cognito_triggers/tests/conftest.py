"""Fixtures de las pruebas del disparador de Cognito."""

from __future__ import annotations

import io
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from testcontainers.community.mongodb import MongoDbContainer

from condo_core.logging import logger
from condo_core.mongo import platform_db, reset_client


@pytest.fixture(scope="session")
def mongo_uri() -> Iterator[str]:
    with MongoDbContainer("mongo:8") as container:
        yield container.get_connection_url()


@pytest.fixture
def mongo(mongo_uri: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("MONGODB_URI", mongo_uri)
    reset_client()
    platform_db()["organizaciones"].delete_many({})
    yield
    reset_client()


@pytest.fixture
def logs() -> Iterator[io.StringIO]:
    handler = logger.registered_handler
    assert isinstance(handler, logging.StreamHandler)
    buffer = io.StringIO()
    previous = handler.setStream(buffer)
    yield buffer
    handler.setStream(previous)


def token_event(groups: list[str], attributes: dict[str, str]) -> dict[str, Any]:
    """Evento ``TokenGeneration_Authentication`` de Pre Token Generation V2."""
    return {
        "version": "2",
        "triggerSource": "TokenGeneration_Authentication",
        "region": "us-east-1",
        "userPoolId": "us-east-1_test",
        "userName": "usuario",
        "callerContext": {"awsSdkVersion": "test", "clientId": "client-test"},
        "request": {
            "userAttributes": {"sub": "sub-1", "email": "persona@example.com", **attributes},
            "groupConfiguration": {
                "groupsToOverride": groups,
                "iamRolesToOverride": [],
                "preferredRole": None,
            },
            "scopes": ["openid", "email"],
        },
        "response": {"claimsAndScopeOverrideDetails": None},
    }
