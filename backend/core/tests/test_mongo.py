from __future__ import annotations

import pytest

from condo_core import mongo as mongo_mod


@pytest.mark.usefixtures("mongo")
def test_platform_and_shared_databases_connect() -> None:
    platform = mongo_mod.platform_db()
    shared = mongo_mod.shared_db()
    assert platform.name == "platform"
    assert shared.name == "shared"
    assert platform.command("ping")["ok"] == 1


@pytest.mark.usefixtures("mongo")
def test_client_is_reused_within_container() -> None:
    assert mongo_mod.get_client() is mongo_mod.get_client()


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        (
            "mongodb+srv://cluster0.example.mongodb.net/",
            {"authMechanism": "MONGODB-AWS", "authSource": "$external", "tls": True},
        ),
        ("mongodb+srv://cluster0.example.mongodb.net/?authMechanism=SCRAM-SHA-256", {}),
        ("mongodb://localhost:27017", {}),
    ],
)
def test_atlas_uri_defaults_to_iam_auth(uri: str, expected: dict[str, object]) -> None:
    assert mongo_mod._client_options(uri) == expected


def test_reset_client_without_client_is_noop() -> None:
    mongo_mod.reset_client()
    mongo_mod.reset_client()
