"""Lambda ``order-status``: consulta y cancelación del pedido por parte del cliente."""

from typing import Any

from app.http import Response, api_handler, dispatch, not_implemented
from app.observability import Logger


def get_order(event: dict[str, Any], log: Logger) -> Response:
    raise not_implemented(event["routeKey"])


def cancel_order(event: dict[str, Any], log: Logger) -> Response:
    raise not_implemented(event["routeKey"])


ROUTES = {
    "GET /api/orders/{orderId}": get_order,
    "POST /api/orders/{orderId}/cancel": cancel_order,
}


@api_handler("order-status")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
