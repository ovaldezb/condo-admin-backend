"""Rutas del módulo organizaciones (contracts/organizaciones.openapi.yaml).

Las historias de usuario registran aquí sus rutas sobre ``router``. La autorización de
SUPER_ADMIN ya se verificó en ``handler.lambda_handler`` antes de resolver cualquier ruta.

Las rutas estáticas (``/organizaciones/catalogos``) van antes que las que tienen ``<tenant_id>``.
"""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from aws_lambda_powertools.event_handler import Response
from aws_lambda_powertools.event_handler.api_gateway import Router

from condo_core.auth import TENANT_ID_PATTERN
from condo_core.errors import DomainError, FieldError
from condo_core.logging import logger
from condo_core.mongo import Document, shared_db
from organizaciones import identity, logos, provisioning, repository
from organizaciones.schemas import LogoCarga, OrganizacionAlta, organizacion_json

router = Router()

_IF_MATCH = re.compile(r'^(?:W/)?"?(\d+)"?$')


# --- Utilidades de petición y respuesta ------------------------------------------------------


def _header(name: str) -> str | None:
    headers = router.current_event.headers or {}
    value = headers.get(name.lower())
    return value.strip() if value else None


def _json_body() -> dict[str, Any]:
    try:
        body = router.current_event.json_body
    except ValueError as error:
        raise _cuerpo_invalido() from error
    if not isinstance(body, dict):
        raise _cuerpo_invalido()
    return body


def _cuerpo_invalido() -> DomainError:
    return DomainError(400, "VALIDACION", "La petición tiene datos inválidos",
                       errores=[FieldError("body", "JSON_INVALIDO",
                                           "El cuerpo debe ser un objeto JSON")])


def _tenant_id(value: str) -> str:
    """Valida el ``tenantId`` de la ruta y lo agrega a los logs como ``target_tenant_id``."""
    if not TENANT_ID_PATTERN.fullmatch(value):
        raise repository.not_found()
    logger.append_keys(target_tenant_id=value)
    return value


def _if_match() -> int:
    value = _header("If-Match")
    if value is None:
        raise DomainError(428, "IF_MATCH_REQUERIDO",
                          "Se requiere el encabezado If-Match con el ETag de la última lectura")
    match = _IF_MATCH.fullmatch(value)
    if match is None:
        raise DomainError(412, "VERSION_DESACTUALIZADA",
                          "Otro usuario modificó la organización; vuelve a consultarla")
    return int(match.group(1))


def _idempotency_key() -> str:
    value = _header("Idempotency-Key")
    if value is None:
        raise DomainError(428, "IDEMPOTENCY_KEY_REQUERIDA",
                          "Se requiere el encabezado Idempotency-Key")
    try:
        return str(uuid.UUID(value))
    except ValueError as error:
        raise DomainError(400, "VALIDACION", "La petición tiene datos inválidos",
                          errores=[FieldError("Idempotency-Key", "UUID_INVALIDO",
                                              "Debe ser un UUID")]) from error


def _etag(doc: Document) -> str:
    return f'"{doc["version"]}"'


def _json(status: int, body: Any, headers: dict[str, str] | None = None) -> Response[str]:
    return Response(status_code=status, content_type="application/json",
                    body=json.dumps(body, ensure_ascii=False), headers=headers or {})


def _organizacion(doc: Document, status: int = 200,
                  extra_headers: dict[str, str] | None = None) -> Response[str]:
    logo = doc.get("logo")
    admin = doc["adminInicial"]
    body = organizacion_json(
        doc,
        logo_url=logos.presigned_url(logo["key"]) if logo else None,
        invitacion=identity.invitation_state(admin["correo"], admin.get("invitacionEnviadaEn")),
    )
    return _json(status, body, {"ETag": _etag(doc), **(extra_headers or {})})


# --- Rutas ---------------------------------------------------------------------------------------


@router.post("/organizaciones")
def crear_organizacion() -> Response[str]:
    """Alta con su primer ADMIN (FR-003 a FR-017). Idempotente por ``Idempotency-Key``."""
    key = _idempotency_key()
    alta = OrganizacionAlta.model_validate(_json_body())
    doc = provisioning.crear_organizacion(alta, key)
    return _organizacion(doc, 201, {"Location": f"/organizaciones/{doc['_id']}"})


@router.get("/organizaciones/catalogos")
def obtener_catalogos() -> Response[str]:
    """Módulos disponibles y regímenes fiscales vigentes para el formulario de alta."""
    modulos = [
        {"clave": m["_id"], "nombre": m["nombre"], "descripcion": m["descripcion"]}
        for m in shared_db()["modulos"].find({"disponible": True}).sort("orden", 1)
    ]
    regimenes = [
        {"clave": r["_id"], "descripcion": r["descripcion"],
         "personaFisica": r["personaFisica"], "personaMoral": r["personaMoral"]}
        for r in shared_db()["regimenes_fiscales"].find({"vigente": True}).sort("_id", 1)
    ]
    return _json(200, {"modulos": modulos, "regimenesFiscales": regimenes})


@router.put("/organizaciones/<tenant_id>/logo")
def reemplazar_logo(tenant_id: str) -> Response[str]:
    """Sube o reemplaza el logotipo (FR-009), con control de versión (FR-025)."""
    tenant_id = _tenant_id(tenant_id)
    version = _if_match()
    actual = repository.get_visible(tenant_id)
    carga = LogoCarga.model_validate(_json_body())
    data, content_type = logos.decode_logo(carga.contenido_base64)

    nueva = logos.put_logo(tenant_id, data, content_type)
    try:
        doc = repository.update_with_version(
            tenant_id, version,
            {"logo": {"key": nueva, "contentType": content_type, "bytes": len(data)}},
        )
    except Exception:
        logos.delete_logo(nueva)
        raise

    anterior = (actual.get("logo") or {}).get("key")
    if anterior and anterior != nueva:
        logos.delete_logo(anterior)
    logger.info("logo_actualizado")
    return _organizacion(doc)


@router.post("/organizaciones/<tenant_id>/admin-inicial/reenviar-invitacion")
def reenviar_invitacion(tenant_id: str) -> Response[str]:
    """Reenvía la invitación del primer ADMIN (FR-026). No cambia ``version``."""
    tenant_id = _tenant_id(tenant_id)
    doc = repository.get_visible(tenant_id)
    if doc["estatus"] == repository.DESHABILITADA:
        raise DomainError(409, "ORGANIZACION_DESHABILITADA",
                          "No se puede reenviar la invitación de una organización deshabilitada")
    correo = doc["adminInicial"]["correo"]
    if identity.user_status(correo) == identity.CONFIRMED:
        raise DomainError(409, "INVITACION_YA_ACEPTADA", "El ADMIN ya activó su cuenta")

    identity.resend_invitation(correo)
    repository.touch_invitacion(tenant_id, repository.now())
    logger.info("invitacion_reenviada")
    return Response(status_code=204)
