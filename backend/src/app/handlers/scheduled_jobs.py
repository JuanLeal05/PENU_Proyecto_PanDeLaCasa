"""Lambda ``scheduled-jobs``: la invoca EventBridge Scheduler, no API Gateway.

Eventos: ``{"job": "reset_stock"}`` (05:30) y ``{"job": "close_day"}`` (18:30).
Un ``job`` desconocido LANZA una excepción a propósito: queda como ERROR en el log y cuenta en la
métrica ``Errors`` de Lambda (sirve para probar las alarmas).
"""

from collections.abc import Callable
from typing import Any

from app.observability import Logger, get_logger


class UnknownJobError(ValueError):
    """El evento trae un ``job`` que no existe."""


def reset_stock(log: Logger) -> int:
    return 0  # Esqueleto (M0): se implementa con el resto de jobs.


def close_day(log: Logger) -> int:
    return 0  # Esqueleto (M0): se implementa con el resto de jobs.


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
    affected = run(log)
    log.info("job_done", job=job, affected=affected)
    return {"job": job, "affected": affected}
