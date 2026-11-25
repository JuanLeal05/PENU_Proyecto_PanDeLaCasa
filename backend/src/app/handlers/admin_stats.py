"""Lambda ``admin-stats`` (JWT): estadísticas del día."""

from typing import Any

from app.http import Response, api_handler, dispatch, not_implemented
from app.observability import Logger


def stats(event: dict[str, Any], log: Logger) -> Response:
    raise not_implemented(event["routeKey"])


ROUTES = {"GET /api/admin/stats": stats}


@api_handler("admin-stats")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
