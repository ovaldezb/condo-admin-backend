"""Resolución de la base de datos de cada organización (principio III).

El tenant sale **sólo** del claim ``tenant_id`` del token. Las funciones de este módulo no aceptan
parámetros de ruta, consulta, encabezados ni cuerpo, para que ningún dato enviado por el cliente
pueda elegir la base de datos.
"""

from __future__ import annotations

from pymongo.database import Database

from condo_core.auth import TENANT_ID_PATTERN, Claims
from condo_core.errors import forbidden
from condo_core.mongo import Document, get_client

TENANT_DB_PREFIX = "t_"


def tenant_db_name(claims: Claims) -> str:
    """Nombre de la base de la organización del token: ``t_<tenant_id>``."""
    tenant_id = claims.tenant_id or ""
    if not TENANT_ID_PATTERN.fullmatch(tenant_id):
        raise forbidden()
    return TENANT_DB_PREFIX + tenant_id


def tenant_db(claims: Claims) -> Database[Document]:
    """Base de datos propia de la organización del token."""
    return get_client()[tenant_db_name(claims)]
