"""Cliente MongoDB compartido por contenedor de Lambda.

La URI se lee de la variable de entorno ``MONGODB_URI``. Si es una URI de Atlas
(``mongodb+srv://``) y no indica mecanismo de autenticación, se usa autenticación IAM
(``MONGODB-AWS``) con TLS, como exige research.md (decisión 6). Una URI ``mongodb://`` sin
mecanismo explícito se usa tal cual; es el caso del contenedor local de las pruebas.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from pymongo import MongoClient
from pymongo.database import Database

PLATFORM_DB = "platform"
SHARED_DB = "shared"

Document = dict[str, Any]


def _client_options(uri: str) -> dict[str, Any]:
    if "authMechanism=" in uri or not uri.startswith("mongodb+srv://"):
        return {}
    return {"authMechanism": "MONGODB-AWS", "authSource": "$external", "tls": True}


@lru_cache(maxsize=1)
def get_client() -> MongoClient[Document]:
    """Devuelve el cliente del contenedor, creándolo en el primer uso."""
    uri = os.environ["MONGODB_URI"]
    return MongoClient(uri, **_client_options(uri))


def reset_client() -> None:
    """Descarta el cliente actual. Sólo para pruebas que cambian ``MONGODB_URI``."""
    if get_client.cache_info().currsize:
        get_client().close()
    get_client.cache_clear()


def platform_db() -> Database[Document]:
    """Base de plataforma: registro de organizaciones, exclusiva de SUPER_ADMIN."""
    return get_client()[PLATFORM_DB]


def shared_db() -> Database[Document]:
    """Base compartida: catálogos globales, de sólo lectura para las organizaciones."""
    return get_client()[SHARED_DB]
