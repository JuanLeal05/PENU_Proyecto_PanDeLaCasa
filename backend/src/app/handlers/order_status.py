"""Lambda ``order-status``: consulta y cancelación del pedido por parte del cliente.

El pedido solo se muestra con ``orderId`` + ``code``. Si el código no coincide se responde 404
(igual que si no existiera) para no permitir enumerar pedidos.
"""

from typing import Any

from app import clock
from app.domain import orders as domain
from app.http import (
    Response,
    api_handler,
    dispatch,
    json_response,
    not_found,
    parse_body,
    path_param,
    query_param,
)
from app.observability import Logger, emit_metric
from app.repositories import orders_repo
from app.repositories.transactions import StaleStatusError, change_status_tx

NOT_FOUND_MESSAGE = "No encontramos ese pedido. Revisa el enlace."


def _load_with_code(order_id: str, code: str | None) -> dict[str, Any]:
    order = orders_repo.get(order_id)
    if order is None or not domain.codes_match(order.get("code"), code):
        raise not_found(NOT_FOUND_MESSAGE)
    return order


def get_order(event: dict[str, Any], log: Logger) -> Response:
    order = _load_with_code(path_param(event, "orderId"), query_param(event, "code"))
    return json_response(200, domain.to_public(order))


def cancel_order(event: dict[str, Any], log: Logger) -> Response:
    order_id = path_param(event, "orderId")
    body = parse_body(event)
    order = _load_with_code(order_id, body.get("code"))

    current = order["status"]
    domain.assert_transition(current, domain.CANCELADO, domain.CUSTOMER)

    now = clock.now()
    entry = domain.history_entry(domain.CANCELADO, now, domain.CUSTOMER)
    try:
        change_status_tx(
            order,
            domain.CANCELADO,
            entry,
            clock.iso(now),
            restore_stock=(current, domain.CANCELADO) in domain.RESTORES_STOCK,
        )
    except StaleStatusError as err:
        # El admin lo movió justo antes: se responde con el estado nuevo como transición inválida.
        latest = orders_repo.get(order_id) or order
        raise domain.invalid_transition(latest["status"], domain.CANCELADO) from err

    log.info("order_cancelled", orderId=order_id, by=domain.CUSTOMER, pickupSlot=order["pickupSlot"])
    emit_metric("OrdersCancelled")
    updated = domain.apply_status(order, domain.CANCELADO, now, domain.CUSTOMER)
    return json_response(200, domain.to_public(updated))


ROUTES = {
    "GET /api/orders/{orderId}": get_order,
    "POST /api/orders/{orderId}/cancel": cancel_order,
}


@api_handler("order-status")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
