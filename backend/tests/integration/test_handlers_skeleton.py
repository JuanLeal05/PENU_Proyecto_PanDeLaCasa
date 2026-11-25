"""Esqueleto M0: los 7 handlers existen en la ruta del contrato 04 §2 y responden según el contrato 02."""

import importlib
import re

import pytest

from conftest import body_of, read_logs

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

PENDING = [
    (path, route)
    for path, routes in CONTRACT.items()
    for route in sorted(routes)
    if route != "GET /api/health"
]


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


def test_health(make_event, lambda_context, set_now):
    set_now("2026-11-27T09:15")
    handler = load("app.handlers.public_availability.handler")
    resp = handler(make_event("GET /api/health"), lambda_context)
    assert resp["statusCode"] == 200
    assert body_of(resp) == {"status": "ok", "env": "test", "time": "2026-11-27T09:15:00-05:00"}


def test_health_hora_real_con_offset(make_event, lambda_context):
    resp = load("app.handlers.public_availability.handler")(make_event("GET /api/health"), lambda_context)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d-05:00", body_of(resp)["time"])


@pytest.mark.parametrize(("handler_path", "route"), PENDING)
def test_rutas_pendientes_responden_501(handler_path, route, make_event, lambda_context):
    resp = load(handler_path)(make_event(route, username="admin-test"), lambda_context)
    assert resp["statusCode"] == 501
    error = body_of(resp)["error"]
    assert error["code"] == "NOT_IMPLEMENTED"
    assert set(error) == {"code", "message", "details"}


def test_ruta_ajena_al_handler_da_404(make_event, lambda_context):
    resp = load("app.handlers.create_order.handler")(make_event("GET /api/health"), lambda_context)
    assert resp["statusCode"] == 404
    assert body_of(resp)["error"]["code"] == "NOT_FOUND"


@pytest.mark.parametrize("job", ["reset_stock", "close_day"])
def test_scheduled_jobs(job, lambda_context, capsys):
    result = load("app.handlers.scheduled_jobs.handler")({"job": job}, lambda_context)
    assert result == {"job": job, "affected": 0}
    [record] = read_logs(capsys.readouterr().out)
    assert (record["message"], record["function"]) == ("job_done", "scheduled-jobs")


@pytest.mark.parametrize("event", [{"job": "borrar_todo"}, {}, None, {"job": 5}])
def test_job_desconocido_lanza_excepcion(event, lambda_context, capsys):
    from app.handlers.scheduled_jobs import UnknownJobError

    with pytest.raises(UnknownJobError):
        load("app.handlers.scheduled_jobs.handler")(event, lambda_context)
    [record] = read_logs(capsys.readouterr().out)
    assert (record["level"], record["message"]) == ("ERROR", "job_failed")
