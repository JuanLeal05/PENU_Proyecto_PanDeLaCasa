"""Lambda ``admin-products`` (JWT): productos, foto (URL prefirmada) e inventario."""

from typing import Any

from app.http import Response, api_handler, dispatch, not_implemented
from app.observability import Logger


def _pending(event: dict[str, Any], log: Logger) -> Response:
    raise not_implemented(event["routeKey"])


ROUTES = {
    "GET /api/admin/products": _pending,
    "POST /api/admin/products": _pending,
    "PUT /api/admin/products/{productId}": _pending,
    "DELETE /api/admin/products/{productId}": _pending,
    "POST /api/admin/products/{productId}/image": _pending,
    "PUT /api/admin/inventory": _pending,
}


@api_handler("admin-products")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
