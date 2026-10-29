"""Aislamiento entre tenants (principio III y IV): la base sale sólo del claim del token."""

from __future__ import annotations

import pytest

from condo_core.auth import Claims, claims_from_event
from condo_core.errors import DomainError
from condo_core.tenancy import tenant_db, tenant_db_name
from condo_core.testing import TENANT_A, TENANT_B, claims_for, http_event


def _event_with_foreign_tenant_everywhere() -> dict[str, object]:
    """Petición del tenant A que intenta colar el tenant B por todas las vías del cliente."""
    return http_event(
        claims_for("ADMIN", TENANT_A),
        method="POST",
        path=f"/configuracion/{TENANT_B}",
        query={"tenant_id": TENANT_B, "tenantId": TENANT_B},
        headers={"x-tenant-id": TENANT_B, "tenant_id": TENANT_B},
        body={"tenant_id": TENANT_B, "tenantId": TENANT_B},
    )


def test_database_comes_only_from_token_claim() -> None:
    claims = claims_from_event(_event_with_foreign_tenant_everywhere())
    assert claims is not None
    assert tenant_db_name(claims) == f"t_{TENANT_A}"


def test_tenant_db_returns_database_of_claim(mongo: str) -> None:
    claims = claims_from_event(_event_with_foreign_tenant_everywhere())
    assert claims is not None
    db = tenant_db(claims)
    assert db.name == f"t_{TENANT_A}"
    assert db.name != f"t_{TENANT_B}"


def test_data_written_by_a_is_invisible_to_b(mongo: str) -> None:
    claims_a = Claims(sub="a", username="a", groups=("ADMIN",), tenant_id=TENANT_A)
    claims_b = Claims(sub="b", username="b", groups=("ADMIN",), tenant_id=TENANT_B)
    tenant_db(claims_a)["notas"].insert_one({"texto": "sólo de A"})

    assert tenant_db(claims_b)["notas"].count_documents({}) == 0
    assert tenant_db(claims_a)["notas"].count_documents({}) == 1


@pytest.mark.parametrize("tenant_id", [None, "", "abc", "A" * 32, "a" * 31, "../" + "a" * 29])
def test_invalid_tenant_is_403(tenant_id: str | None) -> None:
    claims = Claims(sub="s", username="u", groups=("ADMIN",), tenant_id=tenant_id)
    with pytest.raises(DomainError) as exc:
        tenant_db_name(claims)
    assert (exc.value.status, exc.value.code) == (403, "PROHIBIDO")
