"""Constructores de eventos y claims para las pruebas de todos los módulos.

Viven en el paquete común para que las suites de ``core``, de cada módulo y del disparador de
Cognito usen exactamente el mismo formato de evento. No contienen datos reales ni secretos.
"""

from __future__ import annotations

import json
from typing import Any

TENANT_A = "a" * 32
TENANT_B = "b" * 32


def claims_for(role: str | None, tenant_id: str | None = None) -> dict[str, Any] | None:
    """Claims como los deja el autorizador JWT de la HTTP API, o ``None`` sin sesión."""
    if role is None:
        return None
    claims: dict[str, Any] = {
        "sub": f"sub-{role.lower()}",
        "username": f"{role.lower()}@example.com",
        "cognito:groups": f"[{role}]",
        "client_id": "client-test",
    }
    if tenant_id is not None:
        claims["tenant_id"] = tenant_id
    return claims


def http_event(
    claims: dict[str, Any] | None,
    *,
    method: str = "GET",
    path: str = "/organizaciones",
    query: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
    body: Any = None,
    request_id: str = "req-test-1",
) -> dict[str, Any]:
    """Evento de API Gateway HTTP API (payload 2.0)."""
    request_context: dict[str, Any] = {
        "requestId": request_id,
        "http": {"method": method, "path": path, "sourceIp": "203.0.113.10"},
        "routeKey": f"{method} {path}",
        "stage": "$default",
    }
    if claims is not None:
        request_context["authorizer"] = {"jwt": {"claims": claims, "scopes": None}}
    return {
        "version": "2.0",
        "routeKey": f"{method} {path}",
        "rawPath": path,
        "rawQueryString": "&".join(f"{k}={v}" for k, v in (query or {}).items()),
        "queryStringParameters": query,
        "headers": headers or {},
        "body": json.dumps(body) if body is not None else None,
        "isBase64Encoded": False,
        "requestContext": request_context,
    }


class FakeLambdaContext:
    """Contexto mínimo de Lambda para invocar handlers en pruebas."""

    function_name = "condo-test"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:condo-test"

    def __init__(self, aws_request_id: str = "lambda-req-1") -> None:
        self.aws_request_id = aws_request_id
