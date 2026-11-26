from datetime import datetime
from decimal import Decimal

import pytest

from app.clock import BOGOTA
from app.domain import orders as o
from app.http import ApiError

VALID = {
    "customer": {"name": "Ana Pérez", "phone": "3001234567", "email": "ana@example.com"},
    "pickupSlot": "10:00",
    "items": [{"productId": "p-croissant", "quantity": 2}],
    "dataConsent": True,
}


def with_(**changes):
    body = {**VALID, "customer": dict(VALID["customer"])}
    for key, value in changes.items():
        if key.startswith("customer_"):
            body["customer"][key.removeprefix("customer_")] = value
        else:
            body[key] = value
    return body


def fields_of(body) -> list[str]:
    with pytest.raises(ApiError) as info:
        o.validate_create_request(body)
    assert (info.value.status, info.value.code) == (400, "VALIDATION_ERROR")
    return info.value.details["fields"]


# --- validación ---------------------------------------------------------------------------------


def test_request_valido():
    req = o.validate_create_request(VALID)
    assert (req.name, req.phone, req.email, req.pickup_slot) == (
        "Ana Pérez",
        "3001234567",
        "ana@example.com",
        "10:00",
    )
    assert req.lines == (o.OrderLine("p-croissant", 2),)
    assert req.units == 2


def test_email_opcional():
    assert o.validate_create_request(with_(customer_email=None)).email is None
    assert o.validate_create_request(with_(customer_email="")).email is None


def test_fusiona_lineas_repetidas():
    req = o.validate_create_request(
        with_(
            items=[
                {"productId": "p-croissant", "quantity": 2},
                {"productId": "p-pan-queso", "quantity": 1},
                {"productId": "p-croissant", "quantity": 3},
            ]
        )
    )
    assert req.lines == (o.OrderLine("p-croissant", 5), o.OrderLine("p-pan-queso", 1))


@pytest.mark.parametrize(
    "phone", ["2001234567", "300123456", "30012345678", "300-123-4567", 3001234567, None]
)
def test_validation_telefono(phone):
    assert "customer.phone" in fields_of(with_(customer_phone=phone))


@pytest.mark.parametrize("name", ["A", "", "x" * 61, None, "  a  "])
def test_validation_nombre(name):
    assert "customer.name" in fields_of(with_(customer_name=name))


@pytest.mark.parametrize("email", ["sin-arroba", "a@b", 123])
def test_validation_email(email):
    assert "customer.email" in fields_of(with_(customer_email=email))


@pytest.mark.parametrize("consent", [False, None, "true", 1])
def test_validation_sin_consentimiento(consent):
    assert "dataConsent" in fields_of(with_(dataConsent=consent))


def test_validation_21_unidades():
    items = [{"productId": "p-a", "quantity": 11}, {"productId": "p-b", "quantity": 10}]
    assert fields_of(with_(items=items)) == ["items"]


def test_validation_11_lineas():
    items = [{"productId": f"p-{i}", "quantity": 1} for i in range(11)]
    assert fields_of(with_(items=items)) == ["items"]


def test_limites_exactos_son_validos():
    items = [{"productId": f"p-{i}", "quantity": 2} for i in range(10)]
    assert o.validate_create_request(with_(items=items)).units == 20


@pytest.mark.parametrize(
    ("items", "field"),
    [
        ([], "items"),
        (None, "items"),
        ([{"productId": "p-a", "quantity": 0}], "items[0].quantity"),
        ([{"productId": "p-a", "quantity": 1.5}], "items[0].quantity"),
        ([{"productId": "p-a", "quantity": True}], "items[0].quantity"),
        ([{"productId": "P A", "quantity": 1}], "items[0].productId"),
        (["no-es-objeto"], "items[0].productId"),
    ],
)
def test_validation_items(items, field):
    assert field in fields_of(with_(items=items))


@pytest.mark.parametrize("slot", ["10", "10:0", "99:00", None, 1000])
def test_validation_slot(slot):
    assert "pickupSlot" in fields_of(with_(pickupSlot=slot))


def test_validation_reune_todos_los_campos():
    fields = fields_of({"customer": "x", "items": []})
    assert fields == ["customer", "customer.name", "customer.phone", "dataConsent", "pickupSlot", "items"]


# --- código e idempotencia ----------------------------------------------------------------------


def test_generate_code():
    codes = {o.generate_code() for _ in range(200)}
    assert len(codes) > 190
    for code in codes:
        assert len(code) == 6
        assert set(code) <= set(o.CODE_ALPHABET)
        assert not set(code) & set("O0I1")


def test_codes_match():
    assert o.codes_match("K7M2QX", "K7M2QX")
    assert o.codes_match("K7M2QX", " k7m2qx ")
    assert not o.codes_match("K7M2QX", "K7M2QY")
    assert not o.codes_match("K7M2QX", None)
    assert not o.codes_match(None, "K7M2QX")


def test_request_hash_ignora_orden_de_claves():
    a = {"b": 1, "a": {"y": 2, "x": 1}}
    b = {"a": {"x": 1, "y": 2}, "b": 1}
    assert o.request_hash(a) == o.request_hash(b)
    assert o.request_hash(a) != o.request_hash({**a, "b": 2})
    assert len(o.request_hash(a)) == 64


# --- máquina de estados -------------------------------------------------------------------------

ALLOWED = [
    ("CONFIRMADO", "EN_PREPARACION", "admin"),
    ("CONFIRMADO", "CANCELADO", "customer"),
    ("CONFIRMADO", "CANCELADO", "admin"),
    ("EN_PREPARACION", "LISTO_PARA_RECOGER", "admin"),
    ("EN_PREPARACION", "CANCELADO", "admin"),
    ("LISTO_PARA_RECOGER", "ENTREGADO", "admin"),
    ("LISTO_PARA_RECOGER", "NO_RECOGIDO", "admin"),
    ("LISTO_PARA_RECOGER", "NO_RECOGIDO", "system"),
    ("CONFIRMADO", "NO_RECOGIDO", "system"),
    ("EN_PREPARACION", "NO_RECOGIDO", "system"),
]


def test_tabla_de_transiciones_exacta_del_contrato():
    every = [
        (cur, new, actor)
        for cur in o.STATUSES
        for new in o.STATUSES
        for actor in ("customer", "admin", "system")
        if o.can_transition(cur, new, actor)
    ]
    assert sorted(every) == sorted(ALLOWED)


@pytest.mark.parametrize(
    ("current", "new", "actor"),
    [
        ("EN_PREPARACION", "CANCELADO", "customer"),
        ("CONFIRMADO", "NO_RECOGIDO", "admin"),
        ("ENTREGADO", "CANCELADO", "admin"),
        ("CANCELADO", "CONFIRMADO", "admin"),
        ("CONFIRMADO", "ENTREGADO", "admin"),
    ],
)
def test_transiciones_invalidas(current, new, actor):
    with pytest.raises(ApiError) as info:
        o.assert_transition(current, new, actor)
    assert (info.value.status, info.value.code) == (409, "INVALID_TRANSITION")


def test_restores_stock():
    assert {("CONFIRMADO", "CANCELADO"), ("EN_PREPARACION", "CANCELADO")} == o.RESTORES_STOCK


# --- construcción y vistas ----------------------------------------------------------------------

NOW = datetime(2026, 11, 27, 8, 41, 12, tzinfo=BOGOTA)
PRODUCTS = {"p-croissant": {"productId": "p-croissant", "name": "Croissant", "price": Decimal("4500")}}


def make_order():
    req = o.validate_create_request(VALID)
    return o.build_order(req, PRODUCTS, NOW, "order-1", "K7M2QX", "idem-1")


def test_build_order():
    order = make_order()
    assert order["items"] == [
        {"productId": "p-croissant", "name": "Croissant", "unitPrice": 4500, "quantity": 2, "subtotal": 9000}
    ]
    assert order["total"] == 9000
    assert order["status"] == "CONFIRMADO"
    assert order["pickupDate"] == "2026-11-27"
    assert order["slotKey"] == "10:00#2026-11-27T08:41:12-05:00"
    assert order["statusHistory"] == [
        {"status": "CONFIRMADO", "at": "2026-11-27T08:41:12-05:00", "by": "customer"}
    ]
    assert order["customerEmail"] == "ana@example.com"
    assert order["dataConsent"] is True


def test_build_order_sin_email_no_guarda_atributo():
    req = o.validate_create_request(with_(customer_email=None))
    assert "customerEmail" not in o.build_order(req, PRODUCTS, NOW, "o", "C", "k")


def test_to_public_no_expone_datos_personales():
    view = o.to_public(make_order())
    assert set(view) == {
        "orderId",
        "status",
        "statusLabel",
        "pickupDate",
        "pickupSlot",
        "items",
        "total",
        "createdAt",
        "history",
    }
    assert view["statusLabel"] == "Confirmado"
    assert view["history"] == [{"status": "CONFIRMADO", "at": "2026-11-27T08:41:12-05:00"}]
    assert "3001234567" not in str(view)


def test_to_admin_y_apply_status():
    later = datetime(2026, 11, 27, 9, 30, 2, tzinfo=BOGOTA)
    order = o.apply_status(make_order(), "EN_PREPARACION", later, "maria")
    view = o.to_admin(order)
    assert view["code"] == "K7M2QX"
    assert view["customer"] == {"name": "Ana Pérez", "phone": "3001234567", "email": "ana@example.com"}
    assert view["statusLabel"] == "En preparación"
    assert view["history"][-1] == {
        "status": "EN_PREPARACION",
        "at": "2026-11-27T09:30:02-05:00",
        "by": "maria",
    }
    assert order["updatedAt"] == "2026-11-27T09:30:02-05:00"
