"""Saga de alta de organizaciones (research.md, decisión 9; FR-010 a FR-017).

Pasos:

1. Insertar la organización en ``aprovisionando``.
2. Crear al primer ADMIN en Cognito, con su ``custom:tenant_id`` y la invitación.
3. Activar la organización y guardar ``adminInicial.sub`` e ``invitacionEnviadaEn``.

Si un paso falla se compensan los anteriores, y la respuesta es 503 ``ALTA_FALLIDA``: no queda
nada a medias (FR-015). El reconciliador limpia lo que una falla abrupta haya dejado.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta
from typing import Any

from condo_core.errors import DomainError, FieldError
from condo_core.logging import logger
from condo_core.mongo import Document, shared_db
from organizaciones import identity, repository
from organizaciones.schemas import OrganizacionAlta
from organizaciones.validators import regimen_error, tipo_persona

RECONCILIAR_DESPUES_DE = timedelta(minutes=15)

_MENSAJES_REGIMEN = {
    "REGIMEN_INEXISTENTE": "El régimen fiscal no existe en el catálogo del SAT",
    "REGIMEN_NO_VIGENTE": "El régimen fiscal ya no está vigente",
    "REGIMEN_NO_APLICA": "El régimen fiscal no aplica al tipo de persona del RFC",
}


def request_hash(alta: OrganizacionAlta) -> str:
    """SHA-256 del JSON canónico del alta ya validada y normalizada."""
    canonical = json.dumps(alta.model_dump(mode="json", by_alias=True), sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def _validar_catalogos(alta: OrganizacionAlta) -> None:
    """Reglas que dependen de los catálogos compartidos (módulos y regímenes fiscales)."""
    errores: list[FieldError] = []
    disponibles = {
        doc["_id"]
        for doc in shared_db()["modulos"].find(
            {"_id": {"$in": alta.modulos_habilitados}, "disponible": True}, {"_id": 1}
        )
    }
    for modulo in alta.modulos_habilitados:
        if modulo not in disponibles:
            errores.append(FieldError("modulosHabilitados", "MODULO_NO_DISPONIBLE",
                                      f"Módulo no disponible: {modulo}"))

    regimen = shared_db()["regimenes_fiscales"].find_one({"_id": alta.fiscal.regimen_fiscal})
    code = regimen_error(regimen, tipo_persona(alta.fiscal.rfc))
    if code is not None:
        errores.append(FieldError("fiscal.regimenFiscal", code, _MENSAJES_REGIMEN[code]))

    if errores:
        raise DomainError(400, "VALIDACION", "La petición tiene datos inválidos", errores=errores)


def _replay(existente: Document, hash_: str) -> Document:
    """Reintento con la misma ``Idempotency-Key`` (FR-016)."""
    if existente.get("requestHash") != hash_:
        raise DomainError(422, "IDEMPOTENCY_KEY_REUTILIZADA",
                          "La Idempotency-Key ya se usó con un cuerpo distinto")
    if existente["estatus"] == repository.APROVISIONANDO:
        raise DomainError(409, "ALTA_EN_PROCESO",
                          "El alta con esta Idempotency-Key todavía está en proceso")
    return existente


def _documento(alta: OrganizacionAlta, tenant_id: str, key: str, hash_: str,
               ahora: datetime) -> dict[str, Any]:
    datos = alta.model_dump(by_alias=True, exclude_none=True)
    return {
        "_id": tenant_id,
        "estatus": repository.APROVISIONANDO,
        **datos,
        "busqueda": repository.busqueda(alta.nombre_comercial, alta.fiscal.razon_social,
                                        alta.fiscal.rfc),
        "idempotencyKey": key,
        "requestHash": hash_,
        "version": 1,
        "creadoEn": ahora,
        "actualizadoEn": ahora,
    }


def _log_falla(paso: str, error: Exception) -> None:
    """Sólo el tipo de error: los mensajes pueden incluir datos (por ejemplo, un RFC duplicado)."""
    logger.error("alta_fallida", extra={"paso": paso, "error": type(error).__name__})


def _compensar(tenant_id: str, correo: str) -> None:
    """Deshace los pasos de la saga en orden inverso. Cada acción es idempotente.

    El documento se borra sólo después de borrar al usuario: si Cognito falla, el documento se
    queda en ``aprovisionando`` (invisible para la API) y el reconciliador reintenta después.
    """
    identity.delete_admin_if_tenant(correo, tenant_id)
    repository.delete(tenant_id)


def crear_organizacion(alta: OrganizacionAlta, idempotency_key: str) -> Document:
    hash_ = request_hash(alta)
    existente = repository.find_by_idempotency_key(idempotency_key)
    if existente is not None:
        return _replay(existente, hash_)

    _validar_catalogos(alta)
    if repository.rfc_exists(alta.fiscal.rfc):
        raise repository.rfc_duplicado()
    correo = alta.admin_inicial.correo
    if identity.admin_exists(correo):
        raise identity.correo_en_uso()

    tenant_id = secrets.token_hex(16)
    logger.append_keys(target_tenant_id=tenant_id)
    ahora = repository.now()

    try:
        repository.insert_aprovisionando(
            _documento(alta, tenant_id, idempotency_key, hash_, ahora))
    except (repository.IdempotencyKeyEnUso, DomainError) as error:
        # Otra petición ganó la carrera. Si fue la misma (misma llave), se devuelve su resultado
        # aunque MongoDB haya reportado primero el índice único del RFC (FR-016).
        concurrente = repository.find_by_idempotency_key(idempotency_key)
        if concurrente is not None:
            return _replay(concurrente, hash_)
        if isinstance(error, DomainError):
            raise
        raise DomainError(503, "ALTA_FALLIDA", "No se pudo completar el alta") from error
    except Exception as error:
        _log_falla("registro", error)
        raise DomainError(503, "ALTA_FALLIDA", "No se pudo completar el alta") from error

    try:
        sub = identity.create_admin(correo, alta.admin_inicial.nombre, tenant_id)
        repository.set_activa(tenant_id, sub, repository.now())
    except Exception as error:
        _log_falla("admin_o_activacion", error)
        try:
            _compensar(tenant_id, correo)
        except Exception as compensacion:
            # Lo termina el reconciliador; la respuesta sigue siendo ALTA_FALLIDA.
            _log_falla("compensacion", compensacion)
        if isinstance(error, DomainError) and error.code == "CORREO_EN_USO":
            raise
        raise DomainError(503, "ALTA_FALLIDA", "No se pudo completar el alta") from error

    logger.info("organizacion_creada")
    return repository.get_visible(tenant_id)


def reconcile_stale(ahora: datetime | None = None) -> int:
    """Compensa las altas que llevan más de 15 minutos en ``aprovisionando``."""
    limite = (ahora or repository.now()) - RECONCILIAR_DESPUES_DE
    reconciliadas = 0
    for doc in repository.find_stale_aprovisionando(limite):
        try:
            _compensar(doc["_id"], doc["adminInicial"]["correo"])
        except Exception as error:
            logger.error("reconciliacion_fallida",
                         extra={"target_tenant_id": doc["_id"], "error": type(error).__name__})
            continue
        reconciliadas += 1
    logger.info("reconciliacion_terminada", extra={"reconciliadas": reconciliadas})
    return reconciliadas
