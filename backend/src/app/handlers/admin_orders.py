"""Lambda ``admin-orders`` (JWT): pedidos del día y cambio de estado (contratos 01 §2 y 02)."""

from typing import Any

from app import clock
from app.domain import orders as domain
from app.domain.schedule import date_or_today
from app.http import (
    Response,
    admin_username,
    api_handler,
    dispatch,
    json_response,
    not_found,
    parse_body,
    path_param,
    query_param,
    validation_error,
)
from app.observability import Logger, emit_metric
from app.repositories import orders_repo
from app.repositories.transactions import StaleStatusError, change_status_tx

MAX_REASON_LENGTH = 200


def list_orders(event: dict[str, Any], log: Logger) -> Response:
    pickup_date = date_or_today(query_param(event, "date"), clock.now())
    status = query_param(event, "status")
    if status and status not in domain.STATUSES:
        raise validation_error("Estado desconocido.", ["status"])
    orders = orders_repo.query_by_date(pickup_date)  # ya vienen ordenados por slotKey
    if status:
        orders = [order for order in orders if order.get("status") == status]
    return json_response(200, {"date": pickup_date, "orders": [domain.to_admin(order) for order in orders]})


def change_status(event: dict[str, Any], log: Logger) -> Response:
    order_id = path_param(event, "orderId")
    body = parse_body(event)
    new_status = body.get("status")
    reason = body.get("reason")
    fields = []
    if new_status not in domain.STATUSES:
        fields.append("status")
    if reason is not None and (not isinstance(reason, str) or len(reason) > MAX_REASON_LENGTH):
        fields.append("reason")
    if fields:
        raise validation_error("Revisa el cambio de estado.", fields)

    order = orders_repo.get(order_id)
    if order is None:
        raise not_found("El pedido no existe.")

    current = order["status"]
    domain.assert_transition(current, new_status, domain.ADMIN)

    by = admin_username(event)
    now = clock.now()
    # El contrato 03 §2 define statusHistory = {status, at, by}: el motivo queda en el log (ver CR-001).
    entry = domain.history_entry(new_status, now, by)
    try:
        change_status_tx(
            order,
            new_status,
            entry,
            clock.iso(now),
            restore_stock=(current, new_status) in domain.RESTORES_STOCK,
        )
    except StaleStatusError as err:
        latest = orders_repo.get(order_id) or order
        raise domain.invalid_transition(latest["status"], new_status) from err

    log.info(
        "order_status_changed",
        orderId=order_id,
        fromStatus=current,
        toStatus=new_status,
        by=by,
        reason=(reason or "").strip() or None,
    )
    if new_status == domain.CANCELADO:
        emit_metric("OrdersCancelled")
    return json_response(200, domain.to_admin(domain.apply_status(order, new_status, now, by)))


ROUTES = {
    "GET /api/admin/orders": list_orders,
    "PATCH /api/admin/orders/{orderId}/status": change_status,
}


@api_handler("admin-orders")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
