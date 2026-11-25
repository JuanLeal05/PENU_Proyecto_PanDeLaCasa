"""Handlers de M1 contra DynamoDB simulado: availability, create-order y order-status."""

import base64
import json

import pytest

from app.handlers import create_order, order_status, public_availability
from conftest import TEST_ENV, body_of, read_logs, slot_count, stock_of

DATE = "2026-11-27"
KEY_1 = "3f6c2a9e-8f0b-4c1e-9a57-2d1c5b7e4a10"
KEY_2 = "9b1d3c4e-5f60-4a7b-8c9d-0e1f2a3b4c5d"


def order_body(slot="10:00", items=None, **extra):
    return {
        "customer": {"name": "Ana Pérez", "phone": "3001234567", "email": "ana@example.com"},
        "pickupSlot": slot,
        "items": items or [{"productId": "p-croissant", "quantity": 2}],
        "dataConsent": True,
        **extra,
    }


@pytest.fixture
def post_order(make_event, lambda_context, set_now):
    set_now(f"{DATE}T08:41:12")

    def _post(body=None, key=KEY_1, headers=None):
        hdrs = {"Idempotency-Key": key} if key else {}
        hdrs.update(headers or {})
        event = make_event("POST /api/orders", body=order_body() if body is None else body, headers=hdrs)
        return create_order.handler(event, lambda_context)

    return _post


def error_code(resp):
    return body_of(resp)["error"]["code"]


# --- GET /api/availability ----------------------------------------------------------------------


def test_availability(ddb, products, make_event, lambda_context, set_now):
    set_now(f"{DATE}T09:45")
    ddb.Table(TEST_ENV["SLOTS_TABLE"]).put_item(Item={"date": DATE, "slot": "10:30", "count": 3})
    resp = public_availability.handler(make_event("GET /api/availability"), lambda_context)
    assert resp["statusCode"] == 200
    body = body_of(resp)
    assert body["date"] == DATE
    assert body["storeOpen"] is True
    slots = {s["slot"]: s for s in body["slots"]}
    assert slots["10:00"]["available"] is False
    assert slots["10:30"] == {"slot": "10:30", "remaining": 7, "available": True}
    assert body["stock"] == {"p-almojabana": 30, "p-croissant": 42, "p-pan-queso": 0}  # sin inactivos


def test_availability_sin_tablas_configuradas_da_500(monkeypatch, make_event, lambda_context, capsys):
    monkeypatch.delenv("SLOTS_TABLE")
    resp = public_availability.handler(make_event("GET /api/availability"), lambda_context)
    assert resp["statusCode"] == 500
    assert "SLOTS_TABLE" in read_logs(capsys.readouterr().out)[0]["stackTrace"]


# --- POST /api/orders ---------------------------------------------------------------------------


def test_create_order_ok(ddb, products, post_order, capsys):
    resp = post_order()
    assert resp["statusCode"] == 201
    body = body_of(resp)
    assert body["status"] == "CONFIRMADO"
    assert body["statusLabel"] == "Confirmado"
    assert len(body["code"]) == 6
    assert body["pickupDate"] == DATE
    assert body["pickupSlot"] == "10:00"
    assert body["total"] == 9000
    assert body["createdAt"] == "2026-11-27T08:41:12-05:00"
    assert "customer" not in body
    assert stock_of(ddb, "p-croissant") == 40
    assert slot_count(ddb, DATE, "10:00") == 1
    saved = ddb.Table(TEST_ENV["ORDERS_TABLE"]).get_item(Key={"orderId": body["orderId"]})["Item"]
    assert saved["status"] == "CONFIRMADO"
    assert saved["code"] == body["code"]
    out = capsys.readouterr().out
    emf = [json.loads(line) for line in out.splitlines() if '"_aws"' in line]
    assert emf[0]["OrdersCreated"] == 1


def test_logs_mask_pii(ddb, products, post_order, capsys):
    post_order()
    out = capsys.readouterr().out
    assert "3001234567" not in out
    assert "ana@example.com" not in out
    created = next(r for r in read_logs(out) if r["message"] == "order_created")
    assert created["customerPhone"] == "300****567"
    assert (created["pickupSlot"], created["units"], created["function"]) == ("10:00", 2, "create-order")


def test_price_from_db(ddb, products, post_order):
    body = order_body(items=[{"productId": "p-croissant", "quantity": 1, "unitPrice": 1, "subtotal": 1}])
    body["total"] = 1
    resp = post_order(body)
    assert resp["statusCode"] == 201
    assert body_of(resp)["items"][0]["unitPrice"] == 4500
    assert body_of(resp)["total"] == 4500


def test_lineas_repetidas_se_suman(ddb, products, post_order):
    items = [{"productId": "p-croissant", "quantity": 1}, {"productId": "p-croissant", "quantity": 2}]
    body = body_of(post_order(order_body(items=items)))
    assert body["items"][0]["quantity"] == 3
    assert stock_of(ddb, "p-croissant") == 39


def test_slot_full(ddb, products, post_order, capsys):
    ddb.Table(TEST_ENV["SLOTS_TABLE"]).put_item(Item={"date": DATE, "slot": "10:00", "count": 10})
    resp = post_order()
    assert (resp["statusCode"], error_code(resp)) == (409, "SLOT_FULL")
    assert stock_of(ddb, "p-croissant") == 42  # atomicidad
    out = capsys.readouterr().out
    rejected = next(r for r in read_logs(out) if r["message"] == "order_rejected")
    assert (rejected["level"], rejected["code"]) == ("WARNING", "SLOT_FULL")
    emf = next(json.loads(line) for line in out.splitlines() if '"_aws"' in line)
    assert (emf["OrdersRejected"], emf["Reason"]) == (1, "SLOT_FULL")


def test_out_of_stock(ddb, products, post_order):
    resp = post_order(order_body(items=[{"productId": "p-pan-queso", "quantity": 2}]))
    assert (resp["statusCode"], error_code(resp)) == (409, "OUT_OF_STOCK")
    assert body_of(resp)["error"]["details"]["productIds"] == ["p-pan-queso"]
    assert slot_count(ddb, DATE, "10:00") == 0  # el cupo no cambia


@pytest.mark.parametrize("product_id", ["p-no-existe", "p-viejo"])
def test_product_not_found(ddb, products, post_order, product_id):
    resp = post_order(order_body(items=[{"productId": product_id, "quantity": 1}]))
    assert (resp["statusCode"], error_code(resp)) == (409, "PRODUCT_NOT_FOUND")
    assert body_of(resp)["error"]["details"]["productIds"] == [product_id]


@pytest.mark.parametrize("hhmm", ["18:05", "05:59"])
def test_store_closed(ddb, products, post_order, set_now, hhmm):
    set_now(f"{DATE}T{hhmm}")
    resp = post_order(order_body(slot="17:30"))
    assert (resp["statusCode"], error_code(resp)) == (409, "STORE_CLOSED")


@pytest.mark.parametrize("slot", ["09:00", "08:30", "10:15", "18:00"])
def test_slot_not_available(ddb, products, post_order, slot):
    resp = post_order(order_body(slot=slot))  # son las 08:41
    assert (resp["statusCode"], error_code(resp)) == (409, "SLOT_NOT_AVAILABLE")


def test_idempotent_replay(ddb, products, post_order):
    first = post_order()
    second = post_order()
    assert (first["statusCode"], second["statusCode"]) == (201, 200)
    assert body_of(first) == body_of(second)
    assert ddb.Table(TEST_ENV["ORDERS_TABLE"]).scan()["Count"] == 1
    assert stock_of(ddb, "p-croissant") == 40


def test_replay_aunque_la_tienda_ya_cerro(ddb, products, post_order, set_now):
    first = post_order()
    set_now(f"{DATE}T18:10")
    second = post_order()
    assert second["statusCode"] == 200
    assert body_of(second)["orderId"] == body_of(first)["orderId"]


def test_idempotency_conflict(ddb, products, post_order):
    post_order()
    resp = post_order(order_body(slot="11:00"))
    assert (resp["statusCode"], error_code(resp)) == (409, "IDEMPOTENCY_CONFLICT")


def test_claves_distintas_crean_pedidos_distintos(ddb, products, post_order):
    a, b = body_of(post_order(key=KEY_1)), body_of(post_order(key=KEY_2))
    assert a["orderId"] != b["orderId"]
    assert slot_count(ddb, DATE, "10:00") == 2


def test_carrera_de_idempotencia_devuelve_la_ganadora(ddb, products, post_order, monkeypatch):
    """Dos peticiones simultáneas: ambas leen 'no existe', una gana la transacción."""
    winner = body_of(post_order())
    from app.repositories import idempotency_repo

    real_get = idempotency_repo.get
    calls = {"n": 0}

    def first_miss(key):
        calls["n"] += 1
        return None if calls["n"] == 1 else real_get(key)

    monkeypatch.setattr(idempotency_repo, "get", first_miss)
    resp = post_order()
    assert resp["statusCode"] == 200
    assert body_of(resp)["orderId"] == winner["orderId"]
    assert ddb.Table(TEST_ENV["ORDERS_TABLE"]).scan()["Count"] == 1


@pytest.mark.parametrize(
    ("headers_key", "field"),
    [(None, "Idempotency-Key"), ("no-es-uuid", "Idempotency-Key"), (KEY_1.upper(), None)],
)
def test_idempotency_key_header(ddb, products, post_order, headers_key, field):
    resp = post_order(key=headers_key)
    if field is None:
        assert resp["statusCode"] == 201  # mayúsculas se normalizan
    else:
        assert (resp["statusCode"], error_code(resp)) == (400, "VALIDATION_ERROR")
        assert body_of(resp)["error"]["details"]["fields"] == [field]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        (order_body(customer={"name": "Ana", "phone": "123"}), "customer.phone"),
        (order_body(dataConsent=False), "dataConsent"),
        (order_body(items=[{"productId": "p-croissant", "quantity": 21}]), "items"),
        (order_body(items=[{"productId": f"p-{i}", "quantity": 1} for i in range(11)]), "items"),
    ],
)
def test_validation_errors(ddb, products, post_order, body, field):
    resp = post_order(body)
    assert (resp["statusCode"], error_code(resp)) == (400, "VALIDATION_ERROR")
    assert field in body_of(resp)["error"]["details"]["fields"]
    assert ddb.Table(TEST_ENV["ORDERS_TABLE"]).scan()["Count"] == 0


def test_cuerpo_no_json(ddb, post_order):
    resp = post_order("{malo")
    assert (resp["statusCode"], error_code(resp)) == (400, "VALIDATION_ERROR")


# --- GET /api/orders/{orderId} y cancelación ----------------------------------------------------


@pytest.fixture
def created(ddb, products, post_order):
    return body_of(post_order())


def get_order(make_event, ctx, order_id, code):
    event = make_event("GET /api/orders/{orderId}", path={"orderId": order_id}, query={"code": code})
    return order_status.handler(event, ctx)


def cancel(make_event, ctx, order_id, code, base64_body=False):
    raw = json.dumps({"code": code})
    event = make_event("POST /api/orders/{orderId}/cancel", path={"orderId": order_id}, body=raw)
    if base64_body:
        event["body"] = base64.b64encode(raw.encode()).decode()
        event["isBase64Encoded"] = True
    return order_status.handler(event, ctx)


def test_get_order(created, make_event, lambda_context):
    resp = get_order(make_event, lambda_context, created["orderId"], created["code"])
    assert resp["statusCode"] == 200
    body = body_of(resp)
    assert body["orderId"] == created["orderId"]
    assert "code" not in body and "customer" not in body
    assert body["history"] == [{"status": "CONFIRMADO", "at": "2026-11-27T08:41:12-05:00"}]


@pytest.mark.parametrize("code", ["ZZZZZZ", "", None])
def test_get_order_wrong_code(created, make_event, lambda_context, code):
    event = make_event("GET /api/orders/{orderId}", path={"orderId": created["orderId"]})
    if code is not None:
        event["queryStringParameters"] = {"code": code}
    resp = order_status.handler(event, lambda_context)
    assert (resp["statusCode"], error_code(resp)) == (404, "NOT_FOUND")


def test_get_order_inexistente(ddb, make_event, lambda_context):
    resp = get_order(make_event, lambda_context, "no-existe", "K7M2QX")
    assert (resp["statusCode"], error_code(resp)) == (404, "NOT_FOUND")


def test_cancel_restores(ddb, created, make_event, lambda_context, set_now, capsys):
    set_now(f"{DATE}T09:00")
    resp = cancel(make_event, lambda_context, created["orderId"], created["code"], base64_body=True)
    assert resp["statusCode"] == 200
    body = body_of(resp)
    assert (body["status"], body["statusLabel"]) == ("CANCELADO", "Cancelado")
    assert [h["status"] for h in body["history"]] == ["CONFIRMADO", "CANCELADO"]
    assert stock_of(ddb, "p-croissant") == 42
    assert slot_count(ddb, DATE, "10:00") == 0
    emf = [json.loads(line) for line in capsys.readouterr().out.splitlines() if '"_aws"' in line]
    assert emf[-1]["OrdersCancelled"] == 1
    # el GET refleja el estado nuevo
    assert body_of(get_order(make_event, lambda_context, created["orderId"], created["code"]))["status"] == (
        "CANCELADO"
    )


def test_cancel_codigo_errado(ddb, created, make_event, lambda_context):
    resp = cancel(make_event, lambda_context, created["orderId"], "ZZZZZZ")
    assert (resp["statusCode"], error_code(resp)) == (404, "NOT_FOUND")
    assert stock_of(ddb, "p-croissant") == 40


def _set_status(ddb, order_id, status):
    ddb.Table(TEST_ENV["ORDERS_TABLE"]).update_item(
        Key={"orderId": order_id},
        UpdateExpression="SET #s = :s",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status},
    )


@pytest.mark.parametrize("status", ["EN_PREPARACION", "CANCELADO", "ENTREGADO"])
def test_cancel_not_allowed(ddb, created, make_event, lambda_context, status):
    _set_status(ddb, created["orderId"], status)
    resp = cancel(make_event, lambda_context, created["orderId"], created["code"])
    assert (resp["statusCode"], error_code(resp)) == (409, "INVALID_TRANSITION")
    assert stock_of(ddb, "p-croissant") == 40


def test_cancel_carrera_con_el_admin(ddb, created, make_event, lambda_context, monkeypatch):
    """El cliente lee CONFIRMADO, pero el admin lo pasa a EN_PREPARACION antes de escribir."""
    from app.repositories import orders_repo

    real_get = orders_repo.get

    def get_then_admin_moves(order_id):
        order = real_get(order_id)
        _set_status(ddb, order_id, "EN_PREPARACION")
        monkeypatch.setattr(orders_repo, "get", real_get)
        return order

    monkeypatch.setattr(orders_repo, "get", get_then_admin_moves)
    resp = cancel(make_event, lambda_context, created["orderId"], created["code"])
    assert (resp["statusCode"], error_code(resp)) == (409, "INVALID_TRANSITION")
    assert body_of(resp)["error"]["details"]["from"] == "EN_PREPARACION"
    assert stock_of(ddb, "p-croissant") == 40
    assert slot_count(ddb, DATE, "10:00") == 1
