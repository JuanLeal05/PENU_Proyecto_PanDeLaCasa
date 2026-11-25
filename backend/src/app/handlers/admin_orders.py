"""Lambda ``admin-orders`` (JWT): pedidos del día y cambio de estado."""

from typing import Any

from app.http import Response, api_handler, dispatch, not_implemented
from app.observability import Logger


def list_orders(event: dict[str, Any], log: Logger) -> Response:
    raise not_implemented(event["routeKey"])


def change_status(event: dict[str, Any], log: Logger) -> Response:
    raise not_implemented(event["routeKey"])


ROUTES = {
    "GET /api/admin/orders": list_orders,
    "PATCH /api/admin/orders/{orderId}/status": change_status,
}


@api_handler("admin-orders")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
