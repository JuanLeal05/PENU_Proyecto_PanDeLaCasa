"""Lambda ``create-order``: ``POST /api/orders`` (contrato 02 y contrato 01 §3)."""

import json
import re
import uuid
from typing import Any

from app import clock
from app.domain import orders as domain
from app.domain.schedule import is_slot_orderable, is_store_open
from app.http import ApiError, Response, api_handler, dispatch, get_header, json_response, parse_body
from app.observability import Logger, emit_metric, mask_phone
from app.repositories import idempotency_repo, products_repo
from app.repositories.transactions import (
    IdempotencyRaceError,
    OutOfStockError,
    SlotFullError,
    create_order_tx,
)

UUID_V4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

# Rechazos que cuentan en la métrica OrdersRejected (dimensión Reason), contrato 04 §7.
METRIC_REASONS = frozenset({"SLOT_FULL", "OUT_OF_STOCK", "STORE_CLOSED", "SLOT_NOT_AVAILABLE"})


def _idempotency_key(event: dict[str, Any]) -> str:
    key = (get_header(event, "idempotency-key") or "").strip().lower()
    if not UUID_V4_RE.match(key):
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "Falta el header Idempotency-Key o no es un UUID v4.",
            {"fields": ["Idempotency-Key"]},
        )
    return key


def _replay(stored: dict[str, Any], body_hash: str) -> Response:
    """Misma clave: mismo cuerpo → 200 con la respuesta original; otro cuerpo → 409."""
    if stored.get("requestHash") != body_hash:
        raise ApiError(
            409,
            "IDEMPOTENCY_CONFLICT",
            "Esta Idempotency-Key ya se usó con un pedido distinto.",
        )
    return json_response(200, json.loads(stored["response"]))


def _reject(code: str, message: str, details: dict[str, Any] | None = None) -> ApiError:
    return ApiError(409, code, message, details)


def create_order(event: dict[str, Any], log: Logger) -> Response:
    key = _idempotency_key(event)
    body = parse_body(event)
    request = domain.validate_create_request(body)
    body_hash = domain.request_hash(body)
    now = clock.now()

    stored = idempotency_repo.get(key)
    if stored and not idempotency_repo.is_expired(stored, now):
        log.info("order_replayed", orderId=stored.get("orderId"))
        return _replay(stored, body_hash)

    if not is_store_open(now):
        raise _reject("STORE_CLOSED", "La tienda recibe pedidos de 6:00 a.m. a 6:00 p.m.")
    if not is_slot_orderable(request.pickup_slot, now):
        raise _reject(
            "SLOT_NOT_AVAILABLE",
            f"La franja {request.pickup_slot} no está disponible; "
            "elige una que empiece en al menos 30 minutos.",
        )

    products = products_repo.batch_get(line.product_id for line in request.lines)
    missing = [
        line.product_id
        for line in request.lines
        if line.product_id not in products or products[line.product_id].get("active") is not True
    ]
    if missing:
        raise _reject("PRODUCT_NOT_FOUND", "Algún producto ya no está disponible.", {"productIds": missing})

    order_id = str(uuid.uuid4())
    order = domain.build_order(request, products, now, order_id, domain.generate_code(), key)
    response_body = {**domain.to_public(order), "code": order["code"]}
    idem_item = idempotency_repo.build_item(key, order_id, body_hash, json.dumps(response_body), now)

    try:
        create_order_tx(order, [(line.product_id, line.quantity) for line in request.lines], idem_item, now)
    except SlotFullError as err:
        raise _reject("SLOT_FULL", f"La franja {request.pickup_slot} ya no tiene cupos.") from err
    except OutOfStockError as err:
        raise _reject(
            "OUT_OF_STOCK",
            "No hay suficientes unidades de algunos productos.",
            {"productIds": err.product_ids},
        ) from err
    except IdempotencyRaceError:
        # Otra petición con la misma clave ganó la carrera: devolvemos lo que ella guardó.
        winner = idempotency_repo.get(key)
        if not winner:
            raise
        return _replay(winner, body_hash)

    log.info(
        "order_created",
        orderId=order_id,
        pickupSlot=request.pickup_slot,
        units=request.units,
        total=order["total"],
        customerPhone=mask_phone(request.phone),
    )
    emit_metric("OrdersCreated")
    return json_response(201, response_body)


def create_order_route(event: dict[str, Any], log: Logger) -> Response:
    """Envoltura que registra los rechazos de negocio (``order_rejected``) y su métrica."""
    try:
        return create_order(event, log)
    except ApiError as err:
        if err.status in (400, 409):
            log.warning("order_rejected", code=err.code, details=err.details)
        if err.code in METRIC_REASONS:
            emit_metric("OrdersRejected", Reason=err.code)
        raise


ROUTES = {"POST /api/orders": create_order_route}


@api_handler("create-order")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
