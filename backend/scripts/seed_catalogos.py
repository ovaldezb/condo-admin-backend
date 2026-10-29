"""Siembra idempotente de los catálogos compartidos y de los índices de la base de plataforma.

Se ejecuta desde el pipeline de despliegue después de desplegar los módulos. Puede correr las
veces que sea necesario: usa upserts y ``create_index`` no falla si el índice ya existe.

Uso: ``MONGODB_URI=... uv run python scripts/seed_catalogos.py``
"""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

from condo_core.mongo import PLATFORM_DB, SHARED_DB, get_client

MODULOS: list[dict[str, Any]] = [
    {"_id": "condominios", "nombre": "Condominios",
     "descripcion": "Condominios, torres y unidades", "orden": 1},
    {"_id": "condominos", "nombre": "Condóminos",
     "descripcion": "Condóminos y residentes por unidad", "orden": 2},
    {"_id": "cuotas", "nombre": "Cuotas",
     "descripcion": "Cuotas de mantenimiento y estados de cuenta", "orden": 3},
    {"_id": "pagos", "nombre": "Pagos",
     "descripcion": "Pagos en línea de cuotas", "orden": 4},
    {"_id": "avisos", "nombre": "Avisos",
     "descripcion": "Avisos y comunicados a residentes", "orden": 5},
    {"_id": "areas-comunes", "nombre": "Áreas comunes",
     "descripcion": "Reservación de áreas comunes", "orden": 6},
]

# Catálogo c_RegimenFiscal del SAT: (clave, descripción, aplica a física, aplica a moral).
# TODO(SAT): verificar claves, descripciones y aplicabilidad contra el catálogo vigente publicado
# por el SAT antes de sembrar en prod.
REGIMENES_FISCALES: list[tuple[str, str, bool, bool]] = [
    ("601", "General de Ley Personas Morales", False, True),
    ("603", "Personas Morales con Fines no Lucrativos", False, True),
    ("605", "Sueldos y Salarios e Ingresos Asimilados a Salarios", True, False),
    ("606", "Arrendamiento", True, False),
    ("607", "Régimen de Enajenación o Adquisición de Bienes", True, False),
    ("608", "Demás ingresos", True, False),
    ("610", "Residentes en el Extranjero sin Establecimiento Permanente en México", True, True),
    ("611", "Ingresos por Dividendos (socios y accionistas)", True, False),
    ("612", "Personas Físicas con Actividades Empresariales y Profesionales", True, False),
    ("614", "Ingresos por intereses", True, False),
    ("615", "Régimen de los ingresos por obtención de premios", True, False),
    ("616", "Sin obligaciones fiscales", True, False),
    ("620", "Sociedades Cooperativas de Producción que optan por diferir sus ingresos",
     False, True),
    ("621", "Incorporación Fiscal", True, False),
    ("622", "Actividades Agrícolas, Ganaderas, Silvícolas y Pesqueras", False, True),
    ("623", "Opcional para Grupos de Sociedades", False, True),
    ("624", "Coordinados", False, True),
    ("625", "Régimen de las Actividades Empresariales con ingresos a través de Plataformas "
     "Tecnológicas", True, False),
    ("626", "Régimen Simplificado de Confianza", True, True),
]


def seed(client: MongoClient[dict[str, Any]]) -> dict[str, int]:
    """Siembra catálogos e índices. Devuelve cuántos documentos quedaron en cada catálogo."""
    shared = client[SHARED_DB]
    shared["modulos"].bulk_write(
        [UpdateOne({"_id": m["_id"]}, {"$set": {**m, "disponible": True}}, upsert=True)
         for m in MODULOS]
    )
    shared["regimenes_fiscales"].bulk_write(
        [
            UpdateOne(
                {"_id": clave},
                {"$set": {"descripcion": descripcion, "personaFisica": fisica,
                          "personaMoral": moral, "vigente": True}},
                upsert=True,
            )
            for clave, descripcion, fisica, moral in REGIMENES_FISCALES
        ]
    )

    organizaciones = client[PLATFORM_DB]["organizaciones"]
    organizaciones.create_index([("fiscal.rfc", ASCENDING)], unique=True, name="rfc_unico")
    organizaciones.create_index([("idempotencyKey", ASCENDING)], unique=True,
                                name="idempotency_key_unica")
    organizaciones.create_index([("estatus", ASCENDING), ("creadoEn", DESCENDING)],
                                name="estatus_creado")

    return {
        "modulos": shared["modulos"].count_documents({}),
        "regimenes_fiscales": shared["regimenes_fiscales"].count_documents({}),
    }


def main() -> int:
    counts = seed(get_client())
    print(f"Catálogos sembrados: {counts}")  # noqa: T201 - salida del pipeline, sin datos personales
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
