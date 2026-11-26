"""Contrato de los handlers: los 7 existen en la ruta del contrato 04 §2, atienden EXACTAMENTE las rutas
del contrato 02 y ninguna queda sin implementar."""

import importlib
import re

import pytest

from conftest import body_of

# Handler (tal como lo configura Terraform) → rutas que atiende, copiadas del contrato 04 §2.
CONTRACT = {
    "app.handlers.public_availability.handler": {"GET /api/health", "GET /api/availability"},
    "app.handlers.create_order.handler": {"POST /api/orders"},
    "app.handlers.order_status.handler": {
        "GET /api/orders/{orderId}",
        "POST /api/orders/{orderId}/cancel",
    },
    "app.handlers.admin_orders.handler": {
        "GET /api/admin/orders",
        "PATCH /api/admin/orders/{orderId}/status",
    },
    "app.handlers.admin_products.handler": {
        "GET /api/admin/products",
        "POST /api/admin/products",
        "PUT /api/admin/products/{productId}",
        "DELETE /api/admin/products/{productId}",
        "POST /api/admin/products/{productId}/image",
        "PUT /api/admin/inventory",
    },
    "app.handlers.admin_stats.handler": {"GET /api/admin/stats"},
}

ALL_ROUTES = [(path, route) for path, routes in CONTRACT.items() for route in sorted(routes)]


def load(handler_path: str):
    module_name, _, attr = handler_path.rpartition(".")
    return getattr(importlib.import_module(module_name), attr)


@pytest.mark.parametrize("handler_path", list(CONTRACT) + ["app.handlers.scheduled_jobs.handler"])
def test_handler_existe_en_la_ruta_del_contrato(handler_path):
    assert callable(load(handler_path))


@pytest.mark.parametrize("handler_path", list(CONTRACT))
def test_rutas_exactas_del_contrato(handler_path):
    module = importlib.import_module(handler_path.rpartition(".")[0])
    assert set(module.ROUTES) == CONTRACT[handler_path]


@pytest.mark.parametrize(("handler_path", "route"), ALL_ROUTES)
def test_ninguna_ruta_sin_implementar(handler_path, route, ddb, assets_bucket, make_event, lambda_context):
    """Con cuerpo vacío cada ruta responde algo del contrato (200/204/400/404), nunca 500 ni 501."""
    event = make_event(
        route,
        body={},
        path={"orderId": "no-existe", "productId": "p-no-existe"},
        username="admin-test",
    )
    resp = load(handler_path)(event, lambda_context)
    assert resp["statusCode"] in {200, 204, 400, 404}, body_of(resp)


def test_health(make_event, lambda_context, set_now):
    set_now("2026-11-27T09:15")
    handler = load("app.handlers.public_availability.handler")
    resp = handler(make_event("GET /api/health"), lambda_context)
    assert resp["statusCode"] == 200
    assert body_of(resp) == {"status": "ok", "env": "test", "time": "2026-11-27T09:15:00-05:00"}


def test_health_hora_real_con_offset(make_event, lambda_context):
    resp = load("app.handlers.public_availability.handler")(make_event("GET /api/health"), lambda_context)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d-05:00", body_of(resp)["time"])


def test_health_no_necesita_tablas(monkeypatch, make_event, lambda_context):
    for name in ("PRODUCTS_TABLE", "SLOTS_TABLE"):
        monkeypatch.delenv(name)
    resp = load("app.handlers.public_availability.handler")(make_event("GET /api/health"), lambda_context)
    assert resp["statusCode"] == 200


def test_ruta_ajena_al_handler_da_404(make_event, lambda_context):
    resp = load("app.handlers.admin_stats.handler")(make_event("GET /api/health"), lambda_context)
    assert resp["statusCode"] == 404
    assert body_of(resp)["error"]["code"] == "NOT_FOUND"
