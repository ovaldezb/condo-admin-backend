"""Modelos de entrada del módulo organizaciones (contracts/organizaciones.openapi.yaml).

Rechazan campos desconocidos (``extra="forbid"``) y usan nombres camelCase en el JSON. Las reglas
de cada campo son las de data-model.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)
from pydantic.alias_generators import to_camel
from pydantic_core import PydanticCustomError

from organizaciones import validators as v


def _regla(funcion: object) -> AfterValidator:
    """Convierte ``ReglaInvalida`` en un error de Pydantic con su ``code`` como tipo."""

    def _validar(valor: str) -> str:
        try:
            return funcion(valor)  # type: ignore[operator, no-any-return]
        except v.ReglaInvalida as error:
            raise PydanticCustomError(error.code, error.mensaje) from error

    return AfterValidator(_validar)


def _rfc(valor: str) -> str:
    rfc = v.normalize_rfc(valor)
    v.validate_rfc(rfc)
    return rfc


def _correo(valor: str) -> str:
    return valor.lower()


Texto = Annotated[str, StringConstraints(strip_whitespace=True)]
Correo = Annotated[EmailStr, Field(max_length=254), AfterValidator(_correo)]
Telefono = Annotated[str, StringConstraints(pattern=v.TELEFONO.pattern)]
CodigoPostal = Annotated[str, StringConstraints(pattern=v.CODIGO_POSTAL.pattern)]
Dia = Annotated[int, Field(ge=v.DIA_MIN, le=v.DIA_MAX, strict=True)]
Rfc = Annotated[str, _regla(_rfc)]
Estado = Annotated[str, _regla(v.canonical_estado)]


class Esquema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class Contacto(Esquema):
    nombre: Annotated[Texto, StringConstraints(min_length=2, max_length=120)]
    correo: Correo
    telefono: Telefono


class Direccion(Esquema):
    calle: Annotated[Texto, StringConstraints(min_length=1, max_length=150)]
    numero_exterior: Annotated[Texto, StringConstraints(min_length=1, max_length=20)]
    numero_interior: Annotated[Texto, StringConstraints(min_length=1, max_length=20)] | None = None
    colonia: Annotated[Texto, StringConstraints(min_length=1, max_length=100)]
    municipio: Annotated[Texto, StringConstraints(min_length=1, max_length=100)]
    estado: Estado
    codigo_postal: CodigoPostal


class Fiscal(Esquema):
    rfc: Rfc
    razon_social: Annotated[Texto, StringConstraints(min_length=2, max_length=254)]
    regimen_fiscal: Annotated[str, StringConstraints(pattern=v.REGIMEN_CLAVE.pattern)]
    codigo_postal: CodigoPostal


class Facturacion(Esquema):
    dia_corte: Dia
    dia_limite_pago: Dia


class AdminInicialAlta(Esquema):
    nombre: Annotated[Texto, StringConstraints(min_length=2, max_length=120)]
    correo: Correo


class OrganizacionAlta(Esquema):
    nombre_comercial: Annotated[Texto, StringConstraints(min_length=2, max_length=150)]
    contacto: Contacto
    direccion: Direccion | None = None
    fiscal: Fiscal
    modulos_habilitados: Annotated[list[str], Field(min_length=1)]
    facturacion: Facturacion
    admin_inicial: AdminInicialAlta

    @field_validator("modulos_habilitados")
    @classmethod
    def _sin_repetidos(cls, modulos: list[str]) -> list[str]:
        if len(set(modulos)) != len(modulos):
            raise PydanticCustomError("MODULOS_REPETIDOS", "Los módulos no deben repetirse")
        return modulos


class LogoCarga(Esquema):
    content_type: Literal["image/png", "image/jpeg"]
    contenido_base64: str


def _fecha(valor: datetime | None) -> str | None:
    if valor is None:
        return None
    return valor.astimezone(UTC).isoformat().replace("+00:00", "Z")


def organizacion_json(doc: Mapping[str, Any], *, logo_url: str | None,
                      invitacion: str) -> dict[str, Any]:
    """Respuesta ``Organizacion`` del contrato a partir del documento de ``platform``.

    No expone campos internos (``busqueda``, ``idempotencyKey``, ``requestHash``,
    ``adminInicial.sub``) ni la llave del logotipo en S3, sólo una URL firmada.
    """
    admin = doc["adminInicial"]
    respuesta: dict[str, Any] = {
        "tenantId": doc["_id"],
        "estatus": doc["estatus"],
        "nombreComercial": doc["nombreComercial"],
        "contacto": doc["contacto"],
        "fiscal": doc["fiscal"],
        "modulosHabilitados": doc["modulosHabilitados"],
        "facturacion": doc["facturacion"],
        "adminInicial": {
            "nombre": admin["nombre"],
            "correo": admin["correo"],
            "invitacion": invitacion,
            "invitacionEnviadaEn": _fecha(admin.get("invitacionEnviadaEn")),
        },
        "version": doc["version"],
        "creadoEn": _fecha(doc["creadoEn"]),
        "actualizadoEn": _fecha(doc["actualizadoEn"]),
    }
    if doc.get("direccion"):
        respuesta["direccion"] = doc["direccion"]
    if doc.get("logo"):
        respuesta["logo"] = {"url": logo_url, "contentType": doc["logo"]["contentType"],
                             "bytes": doc["logo"]["bytes"]}
    if doc.get("deshabilitadoEn"):
        respuesta["deshabilitadoEn"] = _fecha(doc["deshabilitadoEn"])
    return respuesta
