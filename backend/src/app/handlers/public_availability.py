"""Lambda ``public-availability``: ``GET /api/health`` y ``GET /api/availability``."""

from typing import Any

from app import clock
from app.config import load_settings
from app.domain.schedule import build_availability, today
from app.http import Response, api_handler, dispatch, json_response
from app.observability import Logger
from app.repositories import products_repo, slots_repo


def health(event: dict[str, Any], log: Logger) -> Response:
    """La usa el smoke test del pipeline: no toca DynamoDB."""
    return json_response(200, {"status": "ok", "env": load_settings().env, "time": clock.iso(clock.now())})


def availability(event: dict[str, Any], log: Logger) -> Response:
    """Disponibilidad de HOY: cupos por franja y stock de productos activos (no el catálogo)."""
    now = clock.now()
    counts = slots_repo.counts_for(today(now))
    stock = products_repo.active_stock()
    return json_response(200, build_availability(now, counts, stock))


ROUTES = {
    "GET /api/health": health,
    "GET /api/availability": availability,
}


@api_handler("public-availability")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
