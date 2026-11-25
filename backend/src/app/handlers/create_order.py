"""Lambda ``create-order``: ``POST /api/orders``."""

from typing import Any

from app.http import Response, api_handler, dispatch, not_implemented
from app.observability import Logger


def create_order(event: dict[str, Any], log: Logger) -> Response:
    raise not_implemented(event["routeKey"])


ROUTES = {"POST /api/orders": create_order}


@api_handler("create-order")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
