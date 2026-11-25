"""Lambda ``scheduled-jobs``: la invoca EventBridge Scheduler, no API Gateway (contrato 04 §2).

- ``{"job": "reset_stock"}`` a las 05:30: ``stock = dailyProduction`` en los productos activos (S8).
- ``{"job": "close_day"}`` a las 18:30: todo pedido del día no final pasa a ``NO_RECOGIDO`` (S14).

Un ``job`` desconocido LANZA una excepción a propósito: queda como ERROR en el log y cuenta en la
métrica ``Errors`` de Lambda (sirve para probar las alarmas).
"""

from collections.abc import Callable
from typing import Any

from app import clock
from app.domain import orders as domain
from app.domain.schedule import today
from app.observability import Logger, get_logger
from app.repositories import orders_repo, products_repo
from app.repositories.transactions import StaleStatusError, change_status_tx


class UnknownJobError(ValueError):
    """El evento trae un ``job`` que no existe."""


def reset_stock(log: Logger) -> int:
    now_iso = clock.iso(clock.now())
    affected = 0
    for product in products_repo.scan_active():
        if products_repo.reset_stock(product["productId"], now_iso):
            affected += 1
    return affected


def close_day(log: Logger) -> int:
    """No devuelve stock (el pan ya se hizo). La condición sobre el estado evita pisar a un admin."""
    now = clock.now()
    affected = 0
    for order in orders_repo.query_by_date(today(now)):
        current = order.get("status")
        if current in domain.FINAL_STATUSES or not domain.can_transition(
            current, domain.NO_RECOGIDO, domain.SYSTEM
        ):
            continue
        entry = domain.history_entry(domain.NO_RECOGIDO, now, domain.SYSTEM)
        try:
            change_status_tx(order, domain.NO_RECOGIDO, entry, clock.iso(now), restore_stock=False)
        except StaleStatusError:
            log.warning("close_day_skipped", orderId=order["orderId"], status=current)
            continue
        affected += 1
    return affected


JOBS: dict[str, Callable[[Logger], int]] = {
    "reset_stock": reset_stock,
    "close_day": close_day,
}


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    log = get_logger("scheduled-jobs", context)
    job = (event or {}).get("job")
    run = JOBS.get(job) if isinstance(job, str) else None
    if run is None:
        err = UnknownJobError(f"Job desconocido: {job!r}")
        log.error("job_failed", exc=err, job=job)
        raise err
    try:
        affected = run(log)
    except Exception as exc:
        log.error("job_failed", exc=exc, job=job)
        raise
    log.info("job_done", job=job, affected=affected)
    return {"job": job, "affected": affected}
