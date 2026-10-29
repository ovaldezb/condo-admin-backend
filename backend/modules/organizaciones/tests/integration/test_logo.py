"""Logotipo de la organización (T038, FR-009)."""

from __future__ import annotations

import base64
import re
from collections.abc import Callable
from typing import Any

import boto3
import pytest

from condo_core.mongo import platform_db

pytestmark = pytest.mark.usefixtures("mongo", "aws")

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"\x00" * 64

Call = Callable[..., tuple[int, dict[str, str], Any]]


@pytest.fixture
def tenant_id(crear: Call, alta: Callable[..., dict[str, Any]]) -> str:
    status, _, body = crear(alta())
    assert status == 201
    return str(body["tenantId"])


def _put_logo(super_admin: Call, tenant_id: str, data: bytes, content_type: str = "image/png",
              if_match: str | None = '"1"') -> tuple[int, dict[str, str], Any]:
    headers = {"if-match": if_match} if if_match is not None else {}
    body = {"contentType": content_type, "contenidoBase64": base64.b64encode(data).decode()}
    return super_admin("PUT", f"/organizaciones/{tenant_id}/logo", body, headers)


def _keys(bucket: str) -> list[str]:
    objects = boto3.client("s3").list_objects_v2(Bucket=bucket).get("Contents", [])
    return [o["Key"] for o in objects]


@pytest.mark.parametrize(("data", "tipo", "ext"), [(PNG, "image/png", "png"),
                                                   (JPEG, "image/jpeg", "jpg")])
def test_valid_logo_is_stored(super_admin: Call, tenant_id: str, aws: dict[str, str],
                              data: bytes, tipo: str, ext: str) -> None:
    status, headers, body = _put_logo(super_admin, tenant_id, data, content_type="image/png")

    assert status == 200
    assert headers["ETag"] == '"2"'
    assert body["logo"]["contentType"] == tipo
    assert body["logo"]["bytes"] == len(data)
    assert body["logo"]["url"].startswith("https://")
    (key,) = _keys(aws["logos_bucket"])
    assert re.fullmatch(rf"logos/{tenant_id}/[0-9a-f]{{32}}\.{ext}", key)


def test_pdf_disguised_as_png_is_415(super_admin: Call, tenant_id: str,
                                     aws: dict[str, str]) -> None:
    status, _, body = _put_logo(super_admin, tenant_id, PDF)
    assert (status, body["code"]) == (415, "LOGO_TIPO_NO_SOPORTADO")
    assert _keys(aws["logos_bucket"]) == []


def test_logo_over_2_mib_is_413(super_admin: Call, tenant_id: str) -> None:
    status, _, body = _put_logo(super_admin, tenant_id, PNG + b"\x00" * 2_097_152)
    assert (status, body["code"]) == (413, "LOGO_DEMASIADO_GRANDE")


def test_invalid_base64_is_400(super_admin: Call, tenant_id: str) -> None:
    body = {"contentType": "image/png", "contenidoBase64": "esto no es base64!!"}
    status, _, problem = super_admin("PUT", f"/organizaciones/{tenant_id}/logo", body,
                                     {"if-match": '"1"'})
    assert (status, problem["code"]) == (400, "VALIDACION")


def test_missing_if_match_is_428(super_admin: Call, tenant_id: str) -> None:
    status, _, body = _put_logo(super_admin, tenant_id, PNG, if_match=None)
    assert (status, body["code"]) == (428, "IF_MATCH_REQUERIDO")


@pytest.mark.parametrize("if_match", ['"7"', "basura"])
def test_stale_if_match_is_412_and_new_object_is_removed(
    super_admin: Call, tenant_id: str, aws: dict[str, str], if_match: str
) -> None:
    status, _, body = _put_logo(super_admin, tenant_id, PNG, if_match=if_match)
    assert (status, body["code"]) == (412, "VERSION_DESACTUALIZADA")
    assert _keys(aws["logos_bucket"]) == []


def test_replacing_logo_removes_previous_object(super_admin: Call, tenant_id: str,
                                                aws: dict[str, str]) -> None:
    _put_logo(super_admin, tenant_id, PNG)
    (first_key,) = _keys(aws["logos_bucket"])

    status, headers, body = _put_logo(super_admin, tenant_id, JPEG, if_match='"2"')

    assert (status, headers["ETag"]) == (200, '"3"')
    (second_key,) = _keys(aws["logos_bucket"])
    assert second_key != first_key
    doc = platform_db()["organizaciones"].find_one({"_id": tenant_id})
    assert doc is not None and doc["logo"]["key"] == second_key


def test_unknown_organization_is_404(super_admin: Call) -> None:
    status, _, body = _put_logo(super_admin, "c" * 32, PNG)
    assert (status, body["code"]) == (404, "NO_ENCONTRADA")


def test_malformed_tenant_id_is_404(super_admin: Call) -> None:
    status, _, body = _put_logo(super_admin, "no-es-tenant", PNG)
    assert (status, body["code"]) == (404, "NO_ENCONTRADA")
