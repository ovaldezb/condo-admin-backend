"""Acceso a ``platform.organizaciones`` (data-model.md).

Sólo el módulo organizaciones (SUPER_ADMIN) usa estas funciones.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from condo_core.errors import DomainError
from condo_core.mongo import Document, platform_db
from condo_core.normalize import normalize

APROVISIONANDO = "aprovisionando"
ACTIVA = "activa"
DESHABILITADA = "deshabilitada"


class IdempotencyKeyEnUso(Exception):  # noqa: N818 - nombre de dominio
    """Ya existe una organización con la misma ``Idempotency-Key``."""


def _collection() -> Collection[Document]:
    return platform_db()["organizaciones"]


def now() -> datetime:
    return datetime.now(UTC)


def not_found() -> DomainError:
    return DomainError(404, "NO_ENCONTRADA", "La organización no existe")


def rfc_duplicado() -> DomainError:
    return DomainError(409, "RFC_DUPLICADO", "El RFC ya está registrado en la plataforma")


def busqueda(nombre_comercial: str, razon_social: str, rfc: str) -> str:
    """Campo derivado para la búsqueda sin acentos ni mayúsculas (FR-019)."""
    return normalize(f"{nombre_comercial} {razon_social} {rfc}")


def rfc_exists(rfc: str) -> bool:
    return _collection().count_documents({"fiscal.rfc": rfc}, limit=1) > 0


def insert_aprovisionando(doc: Mapping[str, Any]) -> None:
    """Paso 1 de la saga. El documento no lleva ``adminInicial.sub`` ni
    ``adminInicial.invitacionEnviadaEn``: no existen hasta crear al usuario en Cognito.
    """
    admin = doc["adminInicial"]
    if "sub" in admin or "invitacionEnviadaEn" in admin:
        raise ValueError("adminInicial.sub e invitacionEnviadaEn se fijan al activar")
    try:
        _collection().insert_one(dict(doc))
    except DuplicateKeyError as error:
        key_pattern = (error.details or {}).get("keyPattern", {})
        if "idempotencyKey" in key_pattern:
            raise IdempotencyKeyEnUso from error
        raise rfc_duplicado() from error


def find_by_idempotency_key(key: str) -> Document | None:
    return _collection().find_one({"idempotencyKey": key})


def get(tenant_id: str) -> Document | None:
    return _collection().find_one({"_id": tenant_id})


def get_visible(tenant_id: str) -> Document:
    """Organización activa o deshabilitada; las que están en ``aprovisionando`` no existen."""
    doc = _collection().find_one({"_id": tenant_id, "estatus": {"$ne": APROVISIONANDO}})
    if doc is None:
        raise not_found()
    return doc


def set_activa(tenant_id: str, sub: str, invitacion_enviada_en: datetime) -> None:
    """Paso 3 de la saga: activa la organización y guarda los datos del ADMIN en Cognito."""
    result = _collection().update_one(
        {"_id": tenant_id, "estatus": APROVISIONANDO},
        {"$set": {"estatus": ACTIVA, "adminInicial.sub": sub,
                  "adminInicial.invitacionEnviadaEn": invitacion_enviada_en}},
    )
    if result.matched_count != 1:
        raise RuntimeError("La organización dejó de estar en aprovisionando")


def delete(tenant_id: str) -> None:
    _collection().delete_one({"_id": tenant_id})


def find_stale_aprovisionando(older_than: datetime) -> list[Document]:
    return list(_collection().find(
        {"estatus": APROVISIONANDO, "creadoEn": {"$lt": older_than}},
        {"_id": 1, "adminInicial.correo": 1},
    ))


def update_with_version(
    tenant_id: str,
    expected_version: int,
    set_fields: Mapping[str, Any],
    unset_fields: Iterable[str] = (),
) -> Document:
    """Escritura optimista (FR-025): sólo aplica si ``version`` coincide, y la incrementa."""
    update: dict[str, Any] = {
        "$set": {**set_fields, "actualizadoEn": now()},
        "$inc": {"version": 1},
    }
    unset = {field: "" for field in unset_fields}
    if unset:
        update["$unset"] = unset
    try:
        doc = _collection().find_one_and_update(
            {"_id": tenant_id, "version": expected_version, "estatus": {"$ne": APROVISIONANDO}},
            update,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as error:
        raise rfc_duplicado() from error
    if doc is not None:
        return doc
    get_visible(tenant_id)  # 404 si no existe
    raise DomainError(412, "VERSION_DESACTUALIZADA",
                      "Otro usuario modificó la organización; vuelve a consultarla")


def touch_invitacion(tenant_id: str, fecha: datetime) -> None:
    """Registra el reenvío de la invitación sin cambiar ``version`` ni ``actualizadoEn``
    (data-model.md), para no invalidar la edición en curso de otro SUPER_ADMIN.
    """
    _collection().update_one({"_id": tenant_id},
                             {"$set": {"adminInicial.invitacionEnviadaEn": fecha}})
