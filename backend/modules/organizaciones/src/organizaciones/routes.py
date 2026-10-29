"""Rutas del módulo organizaciones (contracts/organizaciones.openapi.yaml).

Las historias de usuario registran aquí sus rutas sobre ``router``. La autorización de
SUPER_ADMIN ya se verificó en ``handler.lambda_handler`` antes de resolver cualquier ruta.
"""

from __future__ import annotations

from aws_lambda_powertools.event_handler.api_gateway import Router

router = Router()
