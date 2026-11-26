"""Pedidos: validación, código, máquina de estados y vistas (contratos 01 §2, 02 y 03 §2)."""

import hashlib
import json
import re
import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.clock import iso
from app.config import Settings, load_settings
from app.domain.schedule import SLOT_RE, today
from app.http import ApiError, validation_error

# --- Estados (contrato 01 §2) -------------------------------------------------------------------

CONFIRMADO = "CONFIRMADO"
EN_PREPARACION = "EN_PREPARACION"
LISTO_PARA_RECOGER = "LISTO_PARA_RECOGER"
ENTREGADO = "ENTREGADO"
CANCELADO = "CANCELADO"
NO_RECOGIDO = "NO_RECOGIDO"

STATUS_LABELS = {
    CONFIRMADO: "Confirmado",
    EN_PREPARACION: "En preparación",
    LISTO_PARA_RECOGER: "Listo para recoger",
    ENTREGADO: "Entregado",
    CANCELADO: "Cancelado",
    NO_RECOGIDO: "No recogido",
}
STATUSES = tuple(STATUS_LABELS)
FINAL_STATUSES = frozenset({ENTREGADO, CANCELADO, NO_RECOGIDO})

CUSTOMER, ADMIN, SYSTEM = "customer", "admin", "system"

# estado actual → nuevo estado → actores que pueden hacer la transición
ALLOWED_TRANSITIONS: dict[str, dict[str, frozenset[str]]] = {
    CONFIRMADO: {
        EN_PREPARACION: frozenset({ADMIN}),
        CANCELADO: frozenset({CUSTOMER, ADMIN}),
        NO_RECOGIDO: frozenset({SYSTEM}),
    },
    EN_PREPARACION: {
        LISTO_PARA_RECOGER: frozenset({ADMIN}),
        CANCELADO: frozenset({ADMIN}),
        NO_RECOGIDO: frozenset({SYSTEM}),
    },
    LISTO_PARA_RECOGER: {
        ENTREGADO: frozenset({ADMIN}),
        NO_RECOGIDO: frozenset({ADMIN, SYSTEM}),
    },
}

# Transiciones que devuelven el stock y liberan el cupo de la franja.
RESTORES_STOCK = frozenset({(CONFIRMADO, CANCELADO), (EN_PREPARACION, CANCELADO)})


def invalid_transition(current: str, new: str) -> ApiError:
    return ApiError(
        409,
        "INVALID_TRANSITION",
        f"El pedido no puede pasar de {STATUS_LABELS.get(current, current)} a {STATUS_LABELS.get(new, new)}.",
        {"from": current, "to": new},
    )


def can_transition(current: str, new: str, actor: str) -> bool:
    return actor in ALLOWED_TRANSITIONS.get(current, {}).get(new, frozenset())


def assert_transition(current: str, new: str, actor: str) -> None:
    if not can_transition(current, new, actor):
        raise invalid_transition(current, new)


# --- Código del pedido (contrato 03 §2) ---------------------------------------------------------

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin O, 0, I ni 1
CODE_LENGTH = 6


def generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def codes_match(expected: str | None, received: str | None) -> bool:
    """Comparación en tiempo constante (no da pistas para adivinar el código)."""
    if not expected or not isinstance(received, str):
        return False
    return secrets.compare_digest(expected.encode(), received.strip().upper().encode())


# --- Validación del pedido (contrato 01 S7/S10, contrato 02 POST /api/orders) -------------------

PHONE_RE = re.compile(r"^3\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PRODUCT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


@dataclass(frozen=True)
class OrderLine:
    product_id: str
    quantity: int


@dataclass(frozen=True)
class CreateOrderRequest:
    name: str
    phone: str
    email: str | None
    pickup_slot: str
    lines: tuple[OrderLine, ...]

    @property
    def units(self) -> int:
        return sum(line.quantity for line in self.lines)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_create_request(body: Mapping[str, Any], settings: Settings | None = None) -> CreateOrderRequest:
    """Valida el cuerpo y fusiona líneas repetidas. Lanza ``VALIDATION_ERROR`` con ``details.fields``."""
    s = settings or load_settings()
    fields: list[str] = []

    customer = body.get("customer")
    if not isinstance(customer, Mapping):
        customer = {}
        fields.append("customer")

    name = customer.get("name")
    name = name.strip() if isinstance(name, str) else ""
    if not 2 <= len(name) <= 60:
        fields.append("customer.name")

    phone = customer.get("phone")
    phone = phone.strip() if isinstance(phone, str) else ""
    if not PHONE_RE.match(phone):
        fields.append("customer.phone")

    email = customer.get("email")
    if email in (None, ""):
        email = None
    elif not isinstance(email, str) or len(email) > 254 or not EMAIL_RE.match(email.strip()):
        fields.append("customer.email")
    else:
        email = email.strip().lower()

    if body.get("dataConsent") is not True:
        fields.append("dataConsent")

    pickup_slot = body.get("pickupSlot")
    if not isinstance(pickup_slot, str) or not SLOT_RE.match(pickup_slot):
        fields.append("pickupSlot")

    merged: dict[str, int] = {}
    items = body.get("items")
    if not isinstance(items, list) or not items:
        fields.append("items")
        items = []
    for index, item in enumerate(items):
        item = item if isinstance(item, Mapping) else {}
        product_id, quantity = item.get("productId"), item.get("quantity")
        ok = True
        if not isinstance(product_id, str) or not PRODUCT_ID_RE.match(product_id):
            fields.append(f"items[{index}].productId")
            ok = False
        if not _is_int(quantity) or quantity < 1:
            fields.append(f"items[{index}].quantity")
            ok = False
        if ok:
            merged[product_id] = merged.get(product_id, 0) + quantity

    too_many_lines = len(merged) > s.max_lines_per_order
    too_many_units = sum(merged.values()) > s.max_units_per_order
    if too_many_lines or too_many_units:
        fields.append("items")

    if fields:
        raise validation_error(
            f"Revisa los datos del pedido (máximo {s.max_units_per_order} unidades y "
            f"{s.max_lines_per_order} productos distintos).",
            sorted(set(fields), key=fields.index),
        )

    return CreateOrderRequest(
        name=name,
        phone=phone,
        email=email,
        pickup_slot=pickup_slot,
        lines=tuple(OrderLine(pid, qty) for pid, qty in merged.items()),
    )


def request_hash(body: Mapping[str, Any]) -> str:
    """SHA-256 del cuerpo normalizado (JSON con claves ordenadas), contrato 03 §4."""
    normalized = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# --- Construcción del pedido y vistas -----------------------------------------------------------


def history_entry(status: str, at: datetime, by: str, reason: str | None = None) -> dict[str, str]:
    entry = {"status": status, "at": iso(at), "by": by}
    if reason:
        entry["reason"] = reason
    return entry


def build_order(
    request: CreateOrderRequest,
    products: Mapping[str, Mapping[str, Any]],
    now: datetime,
    order_id: str,
    code: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Arma el ítem de ``orders``. Los precios y nombres salen SIEMPRE de ``products`` (la BD)."""
    items = []
    for line in request.lines:
        product = products[line.product_id]
        unit_price = int(product["price"])
        items.append(
            {
                "productId": line.product_id,
                "name": str(product["name"]),
                "unitPrice": unit_price,
                "quantity": line.quantity,
                "subtotal": unit_price * line.quantity,
            }
        )
    created_at = iso(now)
    order: dict[str, Any] = {
        "orderId": order_id,
        "code": code,
        "customerName": request.name,
        "customerPhone": request.phone,
        "dataConsent": True,
        "items": items,
        "total": sum(item["subtotal"] for item in items),
        "pickupDate": today(now),
        "pickupSlot": request.pickup_slot,
        "slotKey": f"{request.pickup_slot}#{created_at}",
        "status": CONFIRMADO,
        "statusHistory": [history_entry(CONFIRMADO, now, CUSTOMER)],
        "idempotencyKey": idempotency_key,
        "createdAt": created_at,
        "updatedAt": created_at,
    }
    if request.email:
        order["customerEmail"] = request.email
    return order


def apply_status(
    order: Mapping[str, Any], new_status: str, now: datetime, by: str, reason: str | None = None
) -> dict[str, Any]:
    """Copia del pedido con el nuevo estado (lo que queda en la BD tras el ``UpdateItem``)."""
    updated = dict(order)
    updated["status"] = new_status
    updated["updatedAt"] = iso(now)
    updated["statusHistory"] = [*order.get("statusHistory", []), history_entry(new_status, now, by, reason)]
    return updated


def _items_view(order: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "productId": item["productId"],
            "name": item["name"],
            "unitPrice": int(item["unitPrice"]),
            "quantity": int(item["quantity"]),
            "subtotal": int(item["subtotal"]),
        }
        for item in order.get("items", [])
    ]


def to_public(order: Mapping[str, Any]) -> dict[str, Any]:
    """``PublicOrder``: sin datos del cliente, sin ``code`` y sin ``by`` en el historial."""
    return {
        "orderId": order["orderId"],
        "status": order["status"],
        "statusLabel": STATUS_LABELS.get(order["status"], order["status"]),
        "pickupDate": order["pickupDate"],
        "pickupSlot": order["pickupSlot"],
        "items": _items_view(order),
        "total": int(order["total"]),
        "createdAt": order["createdAt"],
        "history": [{"status": h["status"], "at": h["at"]} for h in order.get("statusHistory", [])],
    }


def to_admin(order: Mapping[str, Any]) -> dict[str, Any]:
    """``AdminOrder`` = ``PublicOrder`` + ``code`` + ``customer`` + historial con ``by``."""
    view = to_public(order)
    view["code"] = order["code"]
    view["customer"] = {
        "name": order.get("customerName"),
        "phone": order.get("customerPhone"),
        "email": order.get("customerEmail"),
    }
    view["history"] = [dict(h) for h in order.get("statusHistory", [])]
    return view
