from __future__ import annotations

import pytest

from condo_core.auth import Claims, claims_from_event, parse_groups, require_role
from condo_core.errors import DomainError
from condo_core.testing import TENANT_A, claims_for, http_event


def _claims(groups: tuple[str, ...], tenant_id: str | None = None) -> Claims:
    return Claims(sub="s", username="u", groups=groups, tenant_id=tenant_id)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("[SUPER_ADMIN]", ("SUPER_ADMIN",)),
        ("[ADMIN ASISTENTE]", ("ADMIN", "ASISTENTE")),
        ("[ADMIN, ASISTENTE]", ("ADMIN", "ASISTENTE")),
        ("ADMIN", ("ADMIN",)),
        (["ADMIN"], ("ADMIN",)),
        (("ADMIN", "ASISTENTE"), ("ADMIN", "ASISTENTE")),
        ("[]", ()),
        (None, ()),
        (42, ()),
    ],
)
def test_parse_groups(raw: object, expected: tuple[str, ...]) -> None:
    assert parse_groups(raw) == expected


def test_claims_from_event_reads_jwt_claims() -> None:
    event = http_event(claims_for("ADMIN", TENANT_A))
    claims = claims_from_event(event)
    assert claims == Claims(
        sub="sub-admin", username="admin@example.com", groups=("ADMIN",), tenant_id=TENANT_A
    )


def test_claims_from_event_without_authorizer_is_none() -> None:
    assert claims_from_event(http_event(None)) is None
    assert claims_from_event({}) is None


def test_claims_from_event_empty_tenant_is_none() -> None:
    raw = claims_for("SUPER_ADMIN")
    assert raw is not None
    raw["tenant_id"] = ""
    claims = claims_from_event(http_event(raw))
    assert claims is not None
    assert claims.tenant_id is None


def test_without_claims_is_401() -> None:
    with pytest.raises(DomainError) as exc:
        require_role(None, "SUPER_ADMIN")
    assert (exc.value.status, exc.value.code) == (401, "NO_AUTENTICADO")


@pytest.mark.parametrize(
    "claims",
    [
        _claims(()),
        _claims(("SUPER_ADMIN", "ADMIN")),
        _claims(("DESCONOCIDO",)),
        _claims(("SUPER_ADMIN",), tenant_id=TENANT_A),
        _claims(("ADMIN",)),
        _claims(("ADMIN",), tenant_id="ABC"),
        _claims(("ASISTENTE",), tenant_id="A" * 32),
        _claims(("ADMIN",), tenant_id=TENANT_A),
    ],
    ids=[
        "sin-grupos",
        "varios-grupos",
        "grupo-desconocido",
        "super-admin-con-tenant",
        "admin-sin-tenant",
        "admin-tenant-corto",
        "asistente-tenant-mayusculas",
        "rol-no-permitido",
    ],
)
def test_forbidden_cases_are_403(claims: Claims) -> None:
    with pytest.raises(DomainError) as exc:
        require_role(claims, "SUPER_ADMIN", "ASISTENTE")
    assert (exc.value.status, exc.value.code) == (403, "PROHIBIDO")


def test_allowed_roles_pass() -> None:
    super_admin = _claims(("SUPER_ADMIN",))
    admin = _claims(("ADMIN",), tenant_id=TENANT_A)
    assert require_role(super_admin, "SUPER_ADMIN") is super_admin
    assert require_role(admin, "ADMIN", "ASISTENTE") is admin
