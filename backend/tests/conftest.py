"""Fixtures compartidas: variables de entorno del contrato 04, reloj fijo y eventos de API Gateway."""

import json
from collections.abc import Callable
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app import clock

TEST_ENV = {
    "ENV": "test",
    "LOG_LEVEL": "DEBUG",
    "PRODUCTS_TABLE": "pdc-test-products",
    "ORDERS_TABLE": "pdc-test-orders",
    "ORDERS_BY_DATE_INDEX": "byDate",
    "SLOTS_TABLE": "pdc-test-slots",
    "IDEMPOTENCY_TABLE": "pdc-test-idempotency",
    "ASSETS_BUCKET": "pdc-test-assets",
    "ASSETS_BASE_URL": "https://cdn.example.test",
    # Credenciales FICTICIAS para moto: nunca se habla con AWS real.
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
}


@pytest.fixture(autouse=True)
def app_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    return TEST_ENV


@pytest.fixture
def set_now(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], datetime]:
    """Fija ``app.clock.now`` a una hora de Bogotá: ``set_now("2026-11-27T09:45")``."""

    def _set(value: str) -> datetime:
        fixed = datetime.fromisoformat(value).replace(tzinfo=clock.BOGOTA)
        monkeypatch.setattr(clock, "now", lambda: fixed)
        return fixed

    return _set


@pytest.fixture
def lambda_context() -> SimpleNamespace:
    return SimpleNamespace(aws_request_id="req-test-0001", function_name="pdc-test-fn")


@pytest.fixture
def make_event() -> Callable[..., dict[str, Any]]:
    """Construye un evento HTTP API (payload 2.0)."""

    def _make(
        route_key: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
        path: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
        username: str | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "version": "2.0",
            "routeKey": route_key,
            "headers": {k.lower(): v for k, v in (headers or {}).items()},
            "isBase64Encoded": False,
            "requestContext": {"requestId": "apigw-req-1"},
        }
        if body is not None:
            event["body"] = body if isinstance(body, str) else json.dumps(body)
        if path:
            event["pathParameters"] = path
        if query:
            event["queryStringParameters"] = query
        if username:
            event["requestContext"]["authorizer"] = {"jwt": {"claims": {"username": username}}}
        return event

    return _make


def read_logs(captured: str) -> list[dict[str, Any]]:
    """Convierte la salida capturada (una línea JSON por evento) en dicts."""
    return [json.loads(line) for line in captured.splitlines() if line.startswith("{")]


def body_of(response: dict[str, Any]) -> Any:
    return json.loads(response["body"]) if response.get("body") else None
