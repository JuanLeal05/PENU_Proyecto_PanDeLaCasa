"""Transacciones contra DynamoDB simulado (moto): atomicidad de cupo, stock e idempotencia."""

import json
from datetime import datetime

import pytest

from app.clock import BOGOTA
from app.domain import orders as o
from app.repositories import idempotency_repo, orders_repo, products_repo, slots_repo
from app.repositories import transactions as tx
from conftest import TEST_ENV, as_plain, get_item, slot_count, stock_of

NOW = datetime(2026, 11, 27, 8, 0, tzinfo=BOGOTA)
DATE = "2026-11-27"


def new_order(products, lines, slot="10:00", order_id="order-1", key="k-1"):
    body = {
        "customer": {"name": "Ana Pérez", "phone": "3001234567"},
        "pickupSlot": slot,
        "items": [{"productId": p, "quantity": q} for p, q in lines],
        "dataConsent": True,
    }
    req = o.validate_create_request(body)
    order = o.build_order(req, products, NOW, order_id, "K7M2QX", key)
    idem = idempotency_repo.build_item(key, order_id, o.request_hash(body), json.dumps({"x": 1}), NOW)
    return order, [(line.product_id, line.quantity) for line in req.lines], idem


def test_create_ok(ddb, products):
    order, lines, idem = new_order(products, [("p-croissant", 2), ("p-almojabana", 3)])
    tx.create_order_tx(order, lines, idem, NOW)

    assert stock_of(ddb, "p-croissant") == 40
    assert stock_of(ddb, "p-almojabana") == 27
    assert slot_count(ddb, DATE, "10:00") == 1
    slot_item = get_item(ddb, "SLOTS_TABLE", date=DATE, slot="10:00")
    assert int(slot_item["expiresAt"]) == slots_repo.expires_at(DATE)
    saved = as_plain(orders_repo.get("order-1"))
    assert saved["status"] == "CONFIRMADO"
    assert saved["total"] == 2 * 4500 + 3 * 2500
    assert idempotency_repo.get("k-1")["orderId"] == "order-1"


def test_slot_full_no_toca_stock(ddb, products):
    ddb.Table(TEST_ENV["SLOTS_TABLE"]).put_item(Item={"date": DATE, "slot": "10:00", "count": 10})
    order, lines, idem = new_order(products, [("p-croissant", 2)])
    with pytest.raises(tx.SlotFullError):
        tx.create_order_tx(order, lines, idem, NOW)
    assert stock_of(ddb, "p-croissant") == 42
    assert slot_count(ddb, DATE, "10:00") == 10
    assert orders_repo.get("order-1") is None
    assert idempotency_repo.get("k-1") is None


def test_out_of_stock_no_toca_cupo(ddb, products):
    order, lines, idem = new_order(products, [("p-croissant", 1), ("p-pan-queso", 2)])
    with pytest.raises(tx.OutOfStockError) as info:
        tx.create_order_tx(order, lines, idem, NOW)
    assert info.value.product_ids == ["p-pan-queso"]
    assert slot_count(ddb, DATE, "10:00") == 0
    assert stock_of(ddb, "p-croissant") == 42


def test_producto_inactivo_falla_como_sin_stock(ddb, products):
    order, lines, idem = new_order(products, [("p-viejo", 1)])
    with pytest.raises(tx.OutOfStockError) as info:
        tx.create_order_tx(order, lines, idem, NOW)
    assert info.value.product_ids == ["p-viejo"]


def test_ultimo_cupo_solo_uno_gana(ddb, products):
    ddb.Table(TEST_ENV["SLOTS_TABLE"]).put_item(Item={"date": DATE, "slot": "10:00", "count": 9})
    first = new_order(products, [("p-croissant", 1)], order_id="o-a", key="k-a")
    second = new_order(products, [("p-croissant", 1)], order_id="o-b", key="k-b")
    tx.create_order_tx(*first, NOW)
    with pytest.raises(tx.SlotFullError):
        tx.create_order_tx(*second, NOW)
    assert slot_count(ddb, DATE, "10:00") == 10
    assert stock_of(ddb, "p-croissant") == 41


def test_carrera_de_idempotencia(ddb, products):
    tx.create_order_tx(*new_order(products, [("p-croissant", 1)], order_id="o-a", key="k-same"), NOW)
    with pytest.raises(tx.IdempotencyRaceError):
        tx.create_order_tx(*new_order(products, [("p-croissant", 1)], order_id="o-b", key="k-same"), NOW)
    assert stock_of(ddb, "p-croissant") == 41
    assert slot_count(ddb, DATE, "10:00") == 1


def test_clave_vencida_se_puede_reutilizar(ddb, products):
    order, lines, idem = new_order(products, [("p-croissant", 1)], order_id="o-a", key="k-old")
    idem["expiresAt"] = int(NOW.timestamp()) - 1
    ddb.Table(TEST_ENV["IDEMPOTENCY_TABLE"]).put_item(Item=idem)
    assert idempotency_repo.is_expired(idempotency_repo.get("k-old"), NOW)
    tx.create_order_tx(*new_order(products, [("p-croissant", 1)], order_id="o-b", key="k-old"), NOW)
    assert idempotency_repo.get("k-old")["orderId"] == "o-b"


def _create(products, ddb, lines=(("p-croissant", 2),)):
    order, line_tuples, idem = new_order(products, list(lines))
    tx.create_order_tx(order, line_tuples, idem, NOW)
    return orders_repo.get(order["orderId"])


def test_cancel_restores(ddb, products):
    order = _create(products, ddb)
    entry = o.history_entry("CANCELADO", NOW, "customer")
    tx.change_status_tx(order, "CANCELADO", entry, "2026-11-27T08:05:00-05:00", restore_stock=True)
    assert stock_of(ddb, "p-croissant") == 42
    assert slot_count(ddb, DATE, "10:00") == 0
    saved = orders_repo.get(order["orderId"])
    assert saved["status"] == "CANCELADO"
    assert [h["status"] for h in saved["statusHistory"]] == ["CONFIRMADO", "CANCELADO"]


def test_cancel_devuelve_stock_aunque_el_producto_este_inactivo(ddb, products):
    order = _create(products, ddb)
    ddb.Table(TEST_ENV["PRODUCTS_TABLE"]).update_item(
        Key={"productId": "p-croissant"},
        UpdateExpression="SET active = :f",
        ExpressionAttributeValues={":f": False},
    )
    entry = o.history_entry("CANCELADO", NOW, "admin")
    tx.change_status_tx(order, "CANCELADO", entry, "x", restore_stock=True)
    assert stock_of(ddb, "p-croissant") == 42


def test_cambio_de_estado_sin_devolver_stock(ddb, products):
    order = _create(products, ddb)
    entry = o.history_entry("EN_PREPARACION", NOW, "maria")
    tx.change_status_tx(order, "EN_PREPARACION", entry, "x", restore_stock=False)
    assert orders_repo.get(order["orderId"])["status"] == "EN_PREPARACION"
    assert stock_of(ddb, "p-croissant") == 40
    assert slot_count(ddb, DATE, "10:00") == 1


@pytest.mark.parametrize("restore", [True, False])
def test_estado_obsoleto(ddb, products, restore):
    order = _create(products, ddb)
    stale = dict(order)
    tx.change_status_tx(order, "EN_PREPARACION", o.history_entry("EN_PREPARACION", NOW, "a"), "x", False)
    with pytest.raises(tx.StaleStatusError):
        tx.change_status_tx(stale, "CANCELADO", o.history_entry("CANCELADO", NOW, "b"), "x", restore)
    assert stock_of(ddb, "p-croissant") == 40  # no se devolvió nada


def test_products_repo(ddb, products):
    assert set(products_repo.batch_get(["p-croissant", "p-nada", "p-croissant"])) == {"p-croissant"}
    assert products_repo.batch_get([]) == {}
    assert products_repo.active_stock() == {"p-croissant": 42, "p-pan-queso": 0, "p-almojabana": 30}
    assert {p["productId"] for p in products_repo.scan_active()} == {
        "p-croissant",
        "p-pan-queso",
        "p-almojabana",
    }
    assert len(products_repo.scan_all()) == 4
    assert products_repo.get("p-viejo")["active"] is False
    assert products_repo.put_if_absent({"productId": "p-nuevo", "stock": 1}) is True
    assert products_repo.put_if_absent({"productId": "p-nuevo", "stock": 99}) is False
    assert stock_of(ddb, "p-nuevo") == 1


def test_slots_repo(ddb):
    table = ddb.Table(TEST_ENV["SLOTS_TABLE"])
    table.put_item(Item={"date": DATE, "slot": "07:00", "count": 10})
    table.put_item(Item={"date": DATE, "slot": "10:30", "count": 3})
    table.put_item(Item={"date": "2026-11-26", "slot": "10:30", "count": 8})
    assert slots_repo.counts_for(DATE) == {"07:00": 10, "10:30": 3}
    assert slots_repo.expires_at(DATE) == int(datetime(2026, 12, 4, tzinfo=BOGOTA).timestamp())
