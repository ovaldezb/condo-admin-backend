"""Catálogos para el formulario de alta (T039)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from condo_core.mongo import shared_db

pytestmark = pytest.mark.usefixtures("mongo", "aws")


def test_only_available_modules_and_current_regimens(super_admin: Callable[..., Any]) -> None:
    shared_db()["modulos"].update_one({"_id": "pagos"}, {"$set": {"disponible": False}})
    shared_db()["regimenes_fiscales"].update_one({"_id": "621"}, {"$set": {"vigente": False}})

    status, _, body = super_admin("GET", "/organizaciones/catalogos")

    assert status == 200
    claves = [m["clave"] for m in body["modulos"]]
    assert claves == ["condominios", "condominos", "cuotas", "avisos", "areas-comunes"]
    assert body["modulos"][0] == {"clave": "condominios", "nombre": "Condominios",
                                  "descripcion": "Condominios, torres y unidades"}

    regimenes = {r["clave"]: r for r in body["regimenesFiscales"]}
    assert "621" not in regimenes
    assert len(regimenes) == 18
    assert regimenes["626"] == {"clave": "626", "descripcion": "Régimen Simplificado de Confianza",
                                "personaFisica": True, "personaMoral": True}
