"""``admin-stats`` y ``scheduled-jobs`` contra DynamoDB simulado."""

import pytest

from app.handlers import admin_orders, admin_stats, scheduled_jobs
from conftest import TEST_ENV, body_of, read_logs, stock_of

DATE = "2026-11-27"


@pytest.fixture
def move(make_event, lambda_context):
    def _move(order_id, *statuses):
        for status in statuses:
            event = make_event(
                "PATCH /api/admin/orders/{orderId}/status",
                body={"status": status},
                path={"orderId": order_id},
                username="maria",
            )
            assert admin_orders.handler(event, lambda_context)["statusCode"] == 200

    return _move


def get_stats(make_event, lambda_context, query=None):
    return admin_stats.handler(
        make_event("GET /api/admin/stats", query=query, username="maria"), lambda_context
    )


def test_stats(place_order, move, make_event, lambda_context, set_now):
    delivered = place_order("10:00", [("p-croissant", 2), ("p-almojabana", 1)])  # 9000 + 2500
    cancelled = place_order("10:00", [("p-croissant", 5)])
    ready = place_order("11:00", [("p-almojabana", 3)])
    place_order("11:00", [("p-croissant", 1)])  # sigue CONFIRMADO
    move(delivered["orderId"], "EN_PREPARACION", "LISTO_PARA_RECOGER", "ENTREGADO")
    move(cancelled["orderId"], "CANCELADO")
    move(ready["orderId"], "EN_PREPARACION", "LISTO_PARA_RECOGER")
    set_now(f"{DATE}T12:00")

    resp = get_stats(make_event, lambda_context)
    assert resp["statusCode"] == 200
    stats = body_of(resp)
    assert stats["date"] == DATE
    assert stats["totalOrders"] == 4
    assert stats["byStatus"] == {
        "CONFIRMADO": 1,
        "EN_PREPARACION": 0,
        "LISTO_PARA_RECOGER": 1,
        "ENTREGADO": 1,
        "CANCELADO": 1,
        "NO_RECOGIDO": 0,
    }
    assert stats["revenueDelivered"] == 11500
    assert stats["unitsByProduct"] == [  # sin el pedido cancelado (5 croissants)
        {"productId": "p-almojabana", "name": "Almojábana", "units": 4},
        {"productId": "p-croissant", "name": "Croissant", "units": 3},
    ]
    slots = {s["slot"]: s["orders"] for s in stats["ordersBySlot"]}
    assert len(slots) == 22
    assert (slots["10:00"], slots["11:00"], slots["07:00"]) == (1, 2, 0)


def test_stats_dia_sin_pedidos(ddb, make_event, lambda_context):
    stats = body_of(get_stats(make_event, lambda_context, {"date": "2026-01-01"}))
    assert stats["totalOrders"] == 0
    assert stats["revenueDelivered"] == 0
    assert stats["unitsByProduct"] == []
    assert set(stats["byStatus"].values()) == {0}


def test_stats_fecha_invalida(ddb, make_event, lambda_context):
    resp = get_stats(make_event, lambda_context, {"date": "ayer"})
    assert resp["statusCode"] == 400


# --- scheduled-jobs -----------------------------------------------------------------------------


def run_job(job, lambda_context):
    return scheduled_jobs.handler({"job": job}, lambda_context)


def test_reset_stock(ddb, place_order, lambda_context, set_now):
    place_order("10:00", [("p-croissant", 2)])
    assert stock_of(ddb, "p-croissant") == 40
    set_now("2026-11-28T05:30")
    result = run_job("reset_stock", lambda_context)
    assert result == {"job": "reset_stock", "affected": 3}  # solo los activos
    assert stock_of(ddb, "p-croissant") == 60
    assert stock_of(ddb, "p-pan-queso") == 60
    assert stock_of(ddb, "p-viejo") == 5  # inactivo: no se toca
    item = ddb.Table(TEST_ENV["PRODUCTS_TABLE"]).get_item(Key={"productId": "p-croissant"})["Item"]
    assert item["updatedAt"] == "2026-11-28T05:30:00-05:00"


def test_close_day(ddb, place_order, move, lambda_context, set_now, capsys):
    confirmed = place_order("10:00")
    ready = place_order("10:30")
    delivered = place_order("11:00")
    cancelled = place_order("11:30")
    move(ready["orderId"], "EN_PREPARACION", "LISTO_PARA_RECOGER")
    move(delivered["orderId"], "EN_PREPARACION", "LISTO_PARA_RECOGER", "ENTREGADO")
    move(cancelled["orderId"], "CANCELADO")
    stock_before = stock_of(ddb, "p-croissant")

    set_now(f"{DATE}T18:30")
    assert run_job("close_day", lambda_context) == {"job": "close_day", "affected": 2}

    orders = ddb.Table(TEST_ENV["ORDERS_TABLE"])

    def status(order):
        return orders.get_item(Key={"orderId": order["orderId"]})["Item"]["status"]

    assert status(confirmed) == "NO_RECOGIDO"
    assert status(ready) == "NO_RECOGIDO"
    assert status(delivered) == "ENTREGADO"
    assert status(cancelled) == "CANCELADO"
    history = orders.get_item(Key={"orderId": ready["orderId"]})["Item"]["statusHistory"]
    assert history[-1] == {"status": "NO_RECOGIDO", "at": "2026-11-27T18:30:00-05:00", "by": "system"}
    assert stock_of(ddb, "p-croissant") == stock_before  # no devuelve stock
    done = [r for r in read_logs(capsys.readouterr().out) if r["message"] == "job_done"]
    assert done[-1]["affected"] == 2

    assert run_job("close_day", lambda_context)["affected"] == 0  # idempotente


def test_close_day_otro_dia_no_toca_nada(ddb, place_order, lambda_context, set_now):
    place_order("10:00")
    set_now("2026-11-28T18:30")
    assert run_job("close_day", lambda_context)["affected"] == 0


def test_close_day_carrera_con_admin(ddb, place_order, lambda_context, set_now, monkeypatch, capsys):
    order = place_order("10:00")
    from app.handlers import scheduled_jobs as module

    real = module.change_status_tx

    def admin_first(o, *args, **kwargs):
        ddb.Table(TEST_ENV["ORDERS_TABLE"]).update_item(
            Key={"orderId": o["orderId"]},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "ENTREGADO"},
        )
        return real(o, *args, **kwargs)

    monkeypatch.setattr(module, "change_status_tx", admin_first)
    set_now(f"{DATE}T18:30")
    assert run_job("close_day", lambda_context)["affected"] == 0
    skipped = [r for r in read_logs(capsys.readouterr().out) if r["message"] == "close_day_skipped"]
    assert skipped[0]["orderId"] == order["orderId"]


@pytest.mark.parametrize("event", [{"job": "borrar_todo"}, {}, None, {"job": 5}])
def test_job_desconocido_lanza_excepcion(event, lambda_context, capsys):
    with pytest.raises(scheduled_jobs.UnknownJobError):
        scheduled_jobs.handler(event, lambda_context)
    [record] = read_logs(capsys.readouterr().out)
    assert (record["level"], record["message"]) == ("ERROR", "job_failed")


def test_job_que_falla_se_registra_y_relanza(monkeypatch, lambda_context, capsys):
    monkeypatch.delenv("PRODUCTS_TABLE")
    with pytest.raises(RuntimeError):
        run_job("reset_stock", lambda_context)
    [record] = read_logs(capsys.readouterr().out)
    assert (record["level"], record["job"]) == ("ERROR", "reset_stock")
    assert "PRODUCTS_TABLE" in record["stackTrace"]
