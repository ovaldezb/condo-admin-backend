"""Reglas de validación de data-model.md (T035)."""

from __future__ import annotations

import pytest

from organizaciones import validators as v

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 16
PDF = b"%PDF-1.7\n" + b"\x00" * 16


@pytest.mark.parametrize(
    ("rfc", "tipo"),
    [("ABC010101AB1", v.PERSONA_MORAL), ("GODE561231GR8", v.PERSONA_FISICA),
     ("&ÑB991231XY9", v.PERSONA_MORAL)],
)
def test_valid_rfc(rfc: str, tipo: str) -> None:
    assert v.validate_rfc(rfc) == tipo


def test_rfc_is_normalized_to_uppercase() -> None:
    assert v.normalize_rfc("  gode561231gr8 ") == "GODE561231GR8"


@pytest.mark.parametrize(
    ("rfc", "code"),
    [
        ("ABC991332XX1", "RFC_FECHA_INVALIDA"),
        ("GODE560230GR8", "RFC_FECHA_INVALIDA"),
        ("XAXX010101000", "RFC_GENERICO"),
        ("XEXX010101000", "RFC_GENERICO"),
        ("AB010101AB1", "RFC_FORMATO_INVALIDO"),
        ("ABC010101AB12", "RFC_FORMATO_INVALIDO"),
        ("ABC-010101-AB1", "RFC_FORMATO_INVALIDO"),
        ("abc010101ab1", "RFC_FORMATO_INVALIDO"),
    ],
)
def test_invalid_rfc(rfc: str, code: str) -> None:
    with pytest.raises(v.ReglaInvalida) as exc:
        v.validate_rfc(rfc)
    assert exc.value.code == code


def test_leap_day_rfc_is_valid() -> None:
    assert v.validate_rfc("ABC000229AB1") == v.PERSONA_MORAL


@pytest.mark.parametrize(
    ("regimen", "tipo", "code"),
    [
        (None, v.PERSONA_MORAL, "REGIMEN_INEXISTENTE"),
        ({"_id": "601", "vigente": False, "personaMoral": True, "personaFisica": False},
         v.PERSONA_MORAL, "REGIMEN_NO_VIGENTE"),
        ({"_id": "605", "vigente": True, "personaMoral": False, "personaFisica": True},
         v.PERSONA_MORAL, "REGIMEN_NO_APLICA"),
        ({"_id": "601", "vigente": True, "personaMoral": True, "personaFisica": False},
         v.PERSONA_FISICA, "REGIMEN_NO_APLICA"),
    ],
)
def test_invalid_regimen(regimen: dict[str, object] | None, tipo: str, code: str) -> None:
    assert v.regimen_error(regimen, tipo) == code


def test_valid_regimen() -> None:
    regimen = {"_id": "626", "vigente": True, "personaMoral": True, "personaFisica": True}
    assert v.regimen_error(regimen, v.PERSONA_FISICA) is None
    assert v.regimen_error(regimen, v.PERSONA_MORAL) is None


@pytest.mark.parametrize("telefono", ["5512345678", "0000000000"])
def test_valid_phone(telefono: str) -> None:
    assert v.TELEFONO.fullmatch(telefono)


@pytest.mark.parametrize("telefono", ["551234567", "55123456789", "55-1234-5678", "+525512345678"])
def test_invalid_phone(telefono: str) -> None:
    assert not v.TELEFONO.fullmatch(telefono)


@pytest.mark.parametrize("cp", ["1234", "123456", "1234a", " 1234"])
def test_invalid_postal_code(cp: str) -> None:
    assert not v.CODIGO_POSTAL.fullmatch(cp)


def test_valid_postal_code() -> None:
    assert v.CODIGO_POSTAL.fullmatch("76000")


@pytest.mark.parametrize(("valor", "esperado"), [("Querétaro", "Querétaro"),
                                                 ("queretaro", "Querétaro"),
                                                 ("  CIUDAD DE MÉXICO ", "Ciudad de México")])
def test_estado_is_canonicalized(valor: str, esperado: str) -> None:
    assert v.canonical_estado(valor) == esperado


def test_there_are_32_estados_and_unknown_is_rejected() -> None:
    assert len(v.ESTADOS) == 32
    with pytest.raises(v.ReglaInvalida) as exc:
        v.canonical_estado("Texas")
    assert exc.value.code == "ESTADO_INVALIDO"


@pytest.mark.parametrize(("dia", "valido"), [(0, False), (1, True), (28, True), (29, False)])
def test_billing_days_range(dia: int, valido: bool) -> None:
    assert (v.DIA_MIN <= dia <= v.DIA_MAX) is valido


@pytest.mark.parametrize(("data", "tipo"), [(PNG, "image/png"), (JPEG, "image/jpeg"),
                                            (PDF, None), (b"", None)])
def test_detect_image_type_by_magic_bytes(data: bytes, tipo: str | None) -> None:
    assert v.detect_image_type(data) == tipo


def test_logo_size_limit_is_2_mib() -> None:
    assert v.MAX_LOGO_BYTES == 2_097_152
