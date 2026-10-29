"""Alta idempotente de un usuario SUPER_ADMIN en el user pool de Cognito.

Sólo se ejecuta desde el workflow manual ``crear-super-admin.yml``, con aprobación del
environment. El correo no se imprime, para que no quede en los logs del pipeline (principio VI).

Uso: ``uv run python scripts/crear_super_admin.py --email persona@example.com
--user-pool-id us-east-1_XXXX`` (o ``USER_POOL_ID`` en el entorno).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

import boto3

SUPER_ADMIN = "SUPER_ADMIN"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SuperAdminError(Exception):
    """Error que impide dar de alta al SUPER_ADMIN."""


def crear_super_admin(cognito: Any, user_pool_id: str, email: str) -> str:
    """Crea el usuario (si no existe) y asegura el grupo. Devuelve ``creado`` o ``existente``."""
    email = email.strip().lower()
    if not EMAIL_PATTERN.fullmatch(email):
        raise SuperAdminError("El correo no tiene un formato válido")

    try:
        user = cognito.admin_get_user(UserPoolId=user_pool_id, Username=email)
    except cognito.exceptions.UserNotFoundException:
        cognito.admin_create_user(
            UserPoolId=user_pool_id,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
        resultado = "creado"
    else:
        attributes = {a["Name"]: a["Value"] for a in user.get("UserAttributes", [])}
        if attributes.get("custom:tenant_id"):
            raise SuperAdminError(
                "El usuario pertenece a una organización; un SUPER_ADMIN no puede tener tenant"
            )
        resultado = "existente"

    cognito.admin_add_user_to_group(UserPoolId=user_pool_id, Username=email, GroupName=SUPER_ADMIN)
    return resultado


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Alta idempotente de un SUPER_ADMIN")
    parser.add_argument("--email", required=True)
    parser.add_argument("--user-pool-id", default=os.environ.get("USER_POOL_ID"))
    args = parser.parse_args(argv)
    if not args.user_pool_id:
        parser.error("falta --user-pool-id o la variable USER_POOL_ID")

    try:
        resultado = crear_super_admin(boto3.client("cognito-idp"), args.user_pool_id, args.email)
    except SuperAdminError as exc:
        print(f"Error: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    print(f"SUPER_ADMIN {resultado}")  # noqa: T201 - sin datos personales
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
