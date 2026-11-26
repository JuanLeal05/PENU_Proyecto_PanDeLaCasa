"""Reloj de la aplicación.

Bogotá es UTC−5 fijo (sin horario de verano), así que no dependemos de ``tzdata``.
Es el ÚNICO lugar donde se consulta la hora: los tests reemplazan ``app.clock.now``.
"""

from datetime import datetime, timedelta, timezone

BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")


def now() -> datetime:
    """Momento actual en hora de Bogotá."""
    return datetime.now(BOGOTA)


def iso(dt: datetime) -> str:
    """Timestamp ISO-8601 con offset y sin microsegundos (``2026-11-27T09:15:00-05:00``)."""
    return dt.astimezone(BOGOTA).isoformat(timespec="seconds")
