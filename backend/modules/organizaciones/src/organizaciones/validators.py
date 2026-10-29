"""Reglas de validación de data-model.md que no dependen de Pydantic.

Cada regla falla con ``ReglaInvalida`` y un ``code`` estable, que los esquemas convierten en
errores por campo (``errores[].code`` de la respuesta problem+json).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date
from typing import Any

from condo_core.normalize import normalize

PERSONA_MORAL = "moral"
PERSONA_FISICA = "fisica"

RFC_MORAL = re.compile(r"^[A-ZÑ&]{3}\d{6}[A-Z\d]{3}$")
RFC_FISICA = re.compile(r"^[A-ZÑ&]{4}\d{6}[A-Z\d]{3}$")
RFC_GENERICOS = frozenset({"XAXX010101000", "XEXX010101000"})

TELEFONO = re.compile(r"^\d{10}$")
CODIGO_POSTAL = re.compile(r"^\d{5}$")
REGIMEN_CLAVE = re.compile(r"^\d{3}$")

DIA_MIN = 1
DIA_MAX = 28

MAX_LOGO_BYTES = 2_097_152
PNG_MAGIC = b"\x89PNG"
JPEG_MAGIC = b"\xff\xd8\xff"

ESTADOS = (
    "Aguascalientes", "Baja California", "Baja California Sur", "Campeche", "Chiapas",
    "Chihuahua", "Ciudad de México", "Coahuila", "Colima", "Durango", "Estado de México",
    "Guanajuato", "Guerrero", "Hidalgo", "Jalisco", "Michoacán", "Morelos", "Nayarit",
    "Nuevo León", "Oaxaca", "Puebla", "Querétaro", "Quintana Roo", "San Luis Potosí", "Sinaloa",
    "Sonora", "Tabasco", "Tamaulipas", "Tlaxcala", "Veracruz", "Yucatán", "Zacatecas",
)
_ESTADOS_NORMALIZADOS = {normalize(estado): estado for estado in ESTADOS}


class ReglaInvalida(ValueError):  # noqa: N818 - nombre de dominio
    def __init__(self, code: str, mensaje: str) -> None:
        super().__init__(mensaje)
        self.code = code
        self.mensaje = mensaje


def normalize_rfc(rfc: str) -> str:
    return rfc.strip().upper()


def _fecha_valida(yymmdd: str) -> bool:
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:])
    for siglo in (2000, 1900):
        try:
            date(siglo + yy, mm, dd)
        except ValueError:
            continue
        return True
    return False


def validate_rfc(rfc: str) -> str:
    """Valida un RFC ya normalizado y devuelve el tipo de persona que indica su longitud."""
    if rfc in RFC_GENERICOS:
        raise ReglaInvalida("RFC_GENERICO", "No se aceptan RFC genéricos")
    if RFC_MORAL.fullmatch(rfc):
        tipo, fecha = PERSONA_MORAL, rfc[3:9]
    elif RFC_FISICA.fullmatch(rfc):
        tipo, fecha = PERSONA_FISICA, rfc[4:10]
    else:
        raise ReglaInvalida("RFC_FORMATO_INVALIDO",
                            "El RFC debe tener 12 (moral) o 13 (física) caracteres válidos")
    if not _fecha_valida(fecha):
        raise ReglaInvalida("RFC_FECHA_INVALIDA", "La fecha contenida en el RFC no es válida")
    return tipo


def tipo_persona(rfc: str) -> str:
    return PERSONA_MORAL if len(rfc) == 12 else PERSONA_FISICA


def regimen_error(regimen: Mapping[str, Any] | None, tipo: str) -> str | None:
    """Código de error si el régimen no existe, no está vigente o no aplica al tipo de persona."""
    if regimen is None:
        return "REGIMEN_INEXISTENTE"
    if not regimen.get("vigente"):
        return "REGIMEN_NO_VIGENTE"
    aplica = regimen.get("personaMoral") if tipo == PERSONA_MORAL else regimen.get("personaFisica")
    return None if aplica else "REGIMEN_NO_APLICA"


def canonical_estado(estado: str) -> str:
    """Nombre oficial de la entidad federativa, sin importar mayúsculas ni acentos."""
    canonical = _ESTADOS_NORMALIZADOS.get(normalize(estado))
    if canonical is None:
        raise ReglaInvalida("ESTADO_INVALIDO", "Debe ser una de las 32 entidades federativas")
    return canonical


def detect_image_type(data: bytes) -> str | None:
    """Tipo real de la imagen según sus primeros bytes, no según su extensión."""
    if data.startswith(PNG_MAGIC):
        return "image/png"
    if data.startswith(JPEG_MAGIC):
        return "image/jpeg"
    return None
