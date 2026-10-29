from __future__ import annotations

import pytest

from condo_core.normalize import normalize


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bajío", "bajio"),
        ("  Condominios   del Bajío ", "condominios del bajio"),
        ("ÑANDÚ", "nandu"),
        ("Administración Pérez & Asociados", "administracion perez & asociados"),
        ("ABC010101AB1", "abc010101ab1"),
        ("", ""),
    ],
)
def test_normalize(text: str, expected: str) -> None:
    assert normalize(text) == expected
