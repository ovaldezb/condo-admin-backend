"""Fixtures comunes de las pruebas de condo_core."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from testcontainers.community.mongodb import MongoDbContainer

from condo_core.mongo import reset_client


@pytest.fixture(scope="session")
def mongo_uri() -> Iterator[str]:
    with MongoDbContainer("mongo:8") as container:
        yield container.get_connection_url()


@pytest.fixture
def mongo(mongo_uri: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Apunta ``MONGODB_URI`` al contenedor y entrega un cliente limpio en cada prueba."""
    monkeypatch.setenv("MONGODB_URI", mongo_uri)
    reset_client()
    yield mongo_uri
    reset_client()
