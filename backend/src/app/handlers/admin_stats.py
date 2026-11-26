"""Lambda ``admin-stats`` (JWT): estadísticas del día (contrato 02 ``GET /api/admin/stats``).

Es un ``Query`` del GSI ``byDate`` + agregación en memoria: con ≤ 220 pedidos/día (techo físico)
no hace falta precalcular nada.
"""

from collections.abc import Iterable, Mapping
from typing import Any

from app import clock
from app.domain import orders as domain
from app.domain.schedule import all_slots, date_or_today
from app.http import Response, api_handler, dispatch, json_response, query_param
from app.observability import Logger
from app.repositories import orders_repo


def compute_stats(pickup_date: str, orders: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Agregados del día.

    - ``revenueDelivered``: solo pedidos ``ENTREGADO``.
    - ``unitsByProduct`` y ``ordersBySlot``: sin contar ``CANCELADO`` (no ocupan cupo ni pan).
    - ``ordersBySlot`` trae las 22 franjas (con 0) para que el panel pinte el eje completo.
    """
    orders = list(orders)
    by_status = dict.fromkeys(domain.STATUSES, 0)
    revenue = 0
    units: dict[str, dict[str, Any]] = {}
    by_slot = dict.fromkeys(all_slots(), 0)

    for order in orders:
        status = order.get("status")
        if status in by_status:
            by_status[status] += 1
        if status == domain.ENTREGADO:
            revenue += int(order.get("total", 0))
        if status == domain.CANCELADO:
            continue
        slot = order.get("pickupSlot")
        if slot in by_slot:
            by_slot[slot] += 1
        for item in order.get("items", []):
            entry = units.setdefault(
                item["productId"], {"productId": item["productId"], "name": item["name"], "units": 0}
            )
            entry["units"] += int(item["quantity"])

    return {
        "date": pickup_date,
        "totalOrders": len(orders),
        "byStatus": by_status,
        "revenueDelivered": revenue,
        "unitsByProduct": sorted(units.values(), key=lambda e: (-e["units"], e["name"])),
        "ordersBySlot": [{"slot": slot, "orders": count} for slot, count in by_slot.items()],
    }


def stats(event: dict[str, Any], log: Logger) -> Response:
    pickup_date = date_or_today(query_param(event, "date"), clock.now())
    return json_response(200, compute_stats(pickup_date, orders_repo.query_by_date(pickup_date)))


ROUTES = {"GET /api/admin/stats": stats}


@api_handler("admin-stats")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
