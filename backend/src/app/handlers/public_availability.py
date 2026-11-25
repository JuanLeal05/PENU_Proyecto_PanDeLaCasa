"""Lambda ``public-availability``: ``GET /api/health`` y ``GET /api/availability``."""

from typing import Any

from app import clock
from app.config import load_settings
from app.http import Response, api_handler, dispatch, json_response, not_implemented
from app.observability import Logger


def health(event: dict[str, Any], log: Logger) -> Response:
    """La usa el smoke test del pipeline: no toca DynamoDB."""
    return json_response(200, {"status": "ok", "env": load_settings().env, "time": clock.iso(clock.now())})


def availability(event: dict[str, Any], log: Logger) -> Response:
    raise not_implemented(event["routeKey"])


ROUTES = {
    "GET /api/health": health,
    "GET /api/availability": availability,
}


@api_handler("public-availability")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
