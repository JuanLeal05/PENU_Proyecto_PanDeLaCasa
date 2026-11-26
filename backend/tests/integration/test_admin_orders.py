"""``admin-orders`` contra DynamoDB simulado."""

import json

import pytest

from app.handlers import admin_orders
from conftest import body_of, read_logs, slot_count, stock_of

DATE = "2026-11-27"


@pytest.fixture
def admin(make_event, lambda_context):
    def _call(route, *, body=None, path=None, query=None):
        event = make_event(route, body=body, path=path, query=query, username="maria")
        return admin_orders.handler(event, lambda_context)

    return _call


def patch(admin, order_id, status, reason=None):
    body = {"status": status} if reason is None else {"status": status, "reason": reason}
    return admin("PATCH /api/admin/orders/{orderId}/status", body=body, path={"orderId": order_id})


def code(resp):
    return body_of(resp)["error"]["code"]


def test_list_orders_por_franja_y_creacion(place_order, admin, set_now):
    late = place_order("11:00", at=f"{DATE}T08:00")
    first = place_order("10:00", at=f"{DATE}T08:05")
    second = place_order("10:00", at=f"{DATE}T08:10")
    set_now(f"{DATE}T09:00")
    resp = admin("GET /api/admin/orders")
    assert resp["statusCode"] == 200
    body = body_of(resp)
    assert body["date"] == DATE
    assert [o["orderId"] for o in body["orders"]] == [first["orderId"], second["orderId"], late["orderId"]]
    order = body["orders"][0]
    assert order["code"] == first["code"]
    assert order["customer"] == {"name": "Cliente Prueba", "phone": "3009998877", "email": None}
    assert order["history"][0]["by"] == "customer"


def test_list_orders_filtros(place_order, admin):
    keep = place_order("10:00")
    other = place_order("10:30")
    patch(admin, other["orderId"], "EN_PREPARACION")
    resp = admin("GET /api/admin/orders", query={"date": DATE, "status": "CONFIRMADO"})
    assert [o["orderId"] for o in body_of(resp)["orders"]] == [keep["orderId"]]
    assert body_of(admin("GET /api/admin/orders", query={"date": "2026-11-26"}))["orders"] == []


@pytest.mark.parametrize(
    ("query", "field"),
    [({"date": "27-11-2026"}, "date"), ({"date": "2026-02-30"}, "date"), ({"status": "PERDIDO"}, "status")],
)
def test_list_orders_parametros_invalidos(ddb, admin, query, field):
    resp = admin("GET /api/admin/orders", query=query)
    assert (resp["statusCode"], code(resp)) == (400, "VALIDATION_ERROR")
    assert body_of(resp)["error"]["details"]["fields"] == [field]


def test_admin_transitions(ddb, place_order, admin, set_now, capsys):
    order = place_order("10:00", [("p-croissant", 2)])
    set_now(f"{DATE}T09:00")
    steps = ["EN_PREPARACION", "LISTO_PARA_RECOGER", "ENTREGADO"]
    for status in steps:
        resp = patch(admin, order["orderId"], status)
        assert resp["statusCode"] == 200, body_of(resp)
        view = body_of(resp)
        assert view["status"] == status
        assert view["history"][-1] == {"status": status, "at": "2026-11-27T09:00:00-05:00", "by": "maria"}
    assert stock_of(ddb, "p-croissant") == 40  # entregar no devuelve stock
    assert slot_count(ddb, DATE, "10:00") == 1

    resp = patch(admin, order["orderId"], "CANCELADO")  # transición inválida desde ENTREGADO
    assert (resp["statusCode"], code(resp)) == (409, "INVALID_TRANSITION")
    logs = [r for r in read_logs(capsys.readouterr().out) if r["message"] == "order_status_changed"]
    assert [(r["fromStatus"], r["toStatus"], r["by"]) for r in logs] == [
        ("CONFIRMADO", "EN_PREPARACION", "maria"),
        ("EN_PREPARACION", "LISTO_PARA_RECOGER", "maria"),
        ("LISTO_PARA_RECOGER", "ENTREGADO", "maria"),
    ]


@pytest.mark.parametrize("before", [[], ["EN_PREPARACION"]])
def test_admin_cancela_y_devuelve_stock(ddb, place_order, admin, before, capsys):
    order = place_order("10:00", [("p-croissant", 2)])
    for status in before:
        patch(admin, order["orderId"], status)
    resp = patch(admin, order["orderId"], "CANCELADO", reason="El cliente llamó")
    assert body_of(resp)["status"] == "CANCELADO"
    assert stock_of(ddb, "p-croissant") == 42
    assert slot_count(ddb, DATE, "10:00") == 0
    out = capsys.readouterr().out
    changed = next(
        r for r in read_logs(out) if r["message"] == "order_status_changed" and r["toStatus"] == "CANCELADO"
    )
    assert changed["reason"] == "El cliente llamó"
    assert "El cliente llamó" not in json.dumps(body_of(resp))  # no se persiste (CR-001)
    assert any('"OrdersCancelled": 1' in line or '"OrdersCancelled":1' in line for line in out.splitlines())


def test_no_recogido_desde_listo_no_devuelve_stock(ddb, place_order, admin):
    order = place_order("10:00", [("p-croissant", 2)])
    for status in ["EN_PREPARACION", "LISTO_PARA_RECOGER", "NO_RECOGIDO"]:
        assert patch(admin, order["orderId"], status)["statusCode"] == 200
    assert stock_of(ddb, "p-croissant") == 40


def test_admin_no_puede_no_recogido_desde_confirmado(place_order, admin):
    order = place_order()
    resp = patch(admin, order["orderId"], "NO_RECOGIDO")  # solo el job de cierre
    assert (resp["statusCode"], code(resp)) == (409, "INVALID_TRANSITION")


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"status": "PERDIDO"}, "status"),
        ({}, "status"),
        ({"status": "CANCELADO", "reason": "x" * 201}, "reason"),
    ],
)
def test_patch_invalido(place_order, admin, body, field):
    order = place_order()
    resp = admin("PATCH /api/admin/orders/{orderId}/status", body=body, path={"orderId": order["orderId"]})
    assert (resp["statusCode"], code(resp)) == (400, "VALIDATION_ERROR")
    assert body_of(resp)["error"]["details"]["fields"] == [field]


def test_patch_inexistente(ddb, admin):
    resp = patch(admin, "no-existe", "EN_PREPARACION")
    assert (resp["statusCode"], code(resp)) == (404, "NOT_FOUND")


def test_dos_admins_no_se_pisan(ddb, place_order, admin, monkeypatch):
    """Ambos leen CONFIRMADO; el segundo en escribir recibe INVALID_TRANSITION."""
    order = place_order()
    from app.repositories import orders_repo

    real_get = orders_repo.get

    def get_then_other_admin_writes(order_id):
        stale = real_get(order_id)
        monkeypatch.setattr(orders_repo, "get", real_get)
        assert patch(admin, order_id, "EN_PREPARACION")["statusCode"] == 200
        return stale

    monkeypatch.setattr(orders_repo, "get", get_then_other_admin_writes)
    resp = patch(admin, order["orderId"], "CANCELADO")
    assert (resp["statusCode"], code(resp)) == (409, "INVALID_TRANSITION")
    assert body_of(resp)["error"]["details"]["from"] == "EN_PREPARACION"
    assert stock_of(ddb, "p-croissant") == 41
