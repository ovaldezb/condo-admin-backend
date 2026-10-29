"""Logotipos en S3 (research.md, decisión 11; FR-009).

El tipo se determina por el contenido real (magic bytes), no por el ``contentType`` declarado.
"""

from __future__ import annotations

import base64
import binascii
import os
import uuid
from functools import lru_cache
from typing import Any

import boto3

from condo_core.errors import DomainError, FieldError
from organizaciones.validators import MAX_LOGO_BYTES, detect_image_type

URL_VIGENCIA_SEGUNDOS = 300
_EXTENSIONES = {"image/png": "png", "image/jpeg": "jpg"}
# Longitud máxima en base64 de MAX_LOGO_BYTES, para rechazar sin decodificar cargas enormes.
_MAX_BASE64 = 4 * ((MAX_LOGO_BYTES + 2) // 3)


@lru_cache(maxsize=1)
def _s3() -> Any:
    return boto3.client("s3")


def reset_clients() -> None:
    """Descarta el cliente del contenedor. Sólo para pruebas."""
    _s3.cache_clear()


def _bucket() -> str:
    return os.environ["LOGOS_BUCKET"]


def demasiado_grande() -> DomainError:
    return DomainError(413, "LOGO_DEMASIADO_GRANDE", "El logotipo no puede superar 2 MB")


def decode_logo(contenido_base64: str) -> tuple[bytes, str]:
    """Decodifica y valida el logotipo. Devuelve ``(bytes, tipo real)``."""
    if len(contenido_base64) > _MAX_BASE64:
        raise demasiado_grande()
    try:
        data = base64.b64decode(contenido_base64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise DomainError(
            400, "VALIDACION", "La petición tiene datos inválidos",
            errores=[FieldError("contenidoBase64", "BASE64_INVALIDO",
                                "El contenido no está codificado en base64")],
        ) from error
    if len(data) > MAX_LOGO_BYTES:
        raise demasiado_grande()
    content_type = detect_image_type(data)
    if content_type is None:
        raise DomainError(415, "LOGO_TIPO_NO_SOPORTADO", "El logotipo debe ser PNG o JPEG")
    return data, content_type


def put_logo(tenant_id: str, data: bytes, content_type: str) -> str:
    """Sube el logotipo a ``logos/<tenantId>/<uuid>.<ext>`` y devuelve su llave."""
    key = f"logos/{tenant_id}/{uuid.uuid4().hex}.{_EXTENSIONES[content_type]}"
    _s3().put_object(Bucket=_bucket(), Key=key, Body=data, ContentType=content_type)
    return key


def delete_logo(key: str) -> None:
    _s3().delete_object(Bucket=_bucket(), Key=key)


def presigned_url(key: str) -> str:
    url: str = _s3().generate_presigned_url(
        "get_object", Params={"Bucket": _bucket(), "Key": key}, ExpiresIn=URL_VIGENCIA_SEGUNDOS,
    )
    return url
