from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest

from condo_core.auth import claims_from_event
from condo_core.logging import (
    PLATFORM_TENANT,
    UNKNOWN_TENANT,
    bind_request,
    inject_lambda_context,
    logger,
)
from condo_core.testing import TENANT_A, claims_for, http_event

CORREO = "contacto.privado@example.com"


@pytest.fixture
def logs() -> Iterator[io.StringIO]:
    """Redirige el handler del logger a un buffer y limpia sus llaves antes y después."""
    handler = logger.registered_handler
    assert isinstance(handler, logging.StreamHandler)
    buffer = io.StringIO()
    previous = handler.setStream(buffer)
    logger.clear_state()
    yield buffer
    logger.clear_state()
    handler.setStream(previous)


def _log_lines(output: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in output.splitlines() if line.startswith("{")]


def test_every_line_has_tenant_and_request_id(logs: io.StringIO) -> None:
    event = http_event(claims_for("ADMIN", TENANT_A), request_id="req-42")
    bind_request(event, claims_from_event(event), lambda_request_id="lambda-1")
    logger.info("primera")
    logger.info("segunda")

    lines = _log_lines(logs.getvalue())
    assert len(lines) == 2
    for line in lines:
        assert line["tenant_id"] == TENANT_A
        assert line["request_id"] == "req-42"
        assert line["lambda_request_id"] == "lambda-1"


def test_super_admin_logs_platform_and_target(logs: io.StringIO) -> None:
    event = http_event(claims_for("SUPER_ADMIN"))
    bind_request(event, claims_from_event(event), target_tenant_id=TENANT_A)
    logger.info("operacion")

    (line,) = _log_lines(logs.getvalue())
    assert line["tenant_id"] == PLATFORM_TENANT
    assert line["target_tenant_id"] == TENANT_A


def test_without_session_logs_unknown_tenant(logs: io.StringIO) -> None:
    bind_request(http_event(None), None)
    logger.info("sin sesion")

    (line,) = _log_lines(logs.getvalue())
    assert line["tenant_id"] == UNKNOWN_TENANT


def test_injected_context_never_logs_event_body(logs: io.StringIO) -> None:
    class _Context:
        function_name = "condo-test"
        memory_limit_in_mb = 128
        invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:condo-test"
        aws_request_id = "lambda-req-1"

    @inject_lambda_context()
    def handler(event: dict[str, object], context: object) -> str:
        logger.info("procesado")
        return "ok"

    event = http_event(claims_for("SUPER_ADMIN"), method="POST", body={"correo": CORREO})
    assert handler(event, _Context()) == "ok"

    output = logs.getvalue()
    assert CORREO not in output
    assert _log_lines(output)[0]["function_request_id"] == "lambda-req-1"
