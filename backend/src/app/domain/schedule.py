"""Horario, franjas y disponibilidad (contrato 01 S2–S6, contrato 02 ``GET /api/availability``)."""

import re
from collections.abc import Mapping
from datetime import date, datetime, timedelta

from app.config import Settings, load_settings
from app.http import validation_error

SLOT_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def to_minutes(hhmm: str) -> int:
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def from_minutes(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def all_slots(settings: Settings | None = None) -> list[str]:
    """Inicio de cada franja: ``["07:00", "07:30", …, "17:30"]`` (22 con los valores del contrato)."""
    s = settings or load_settings()
    first, last = to_minutes(s.first_slot), to_minutes(s.last_slot)
    return [from_minutes(m) for m in range(first, last + 1, s.slot_minutes)]


def today(now: datetime) -> str:
    """Fecha de Bogotá en formato ``YYYY-MM-DD`` (``now`` ya viene en UTC−5)."""
    return now.date().isoformat()


def date_or_today(raw: str | None, now: datetime) -> str:
    """Parámetro ``date`` opcional (``YYYY-MM-DD``); por defecto, hoy en Bogotá."""
    if not raw:
        return today(now)
    try:
        parsed = date.fromisoformat(raw)
    except ValueError:
        parsed = None
    if parsed is None or len(raw) != 10:
        raise validation_error("La fecha debe tener el formato YYYY-MM-DD.", ["date"])
    return parsed.isoformat()


def is_store_open(now: datetime, settings: Settings | None = None) -> bool:
    """``OPEN_TIME <= hora actual < CLOSE_TIME``."""
    s = settings or load_settings()
    current = now.hour * 60 + now.minute + now.second / 60
    return to_minutes(s.open_time) <= current < to_minutes(s.close_time)


def slot_start(slot: str, now: datetime) -> datetime:
    """Inicio de la franja HOY (los pedidos son solo para el mismo día, S6)."""
    hours, minutes = slot.split(":")
    return now.replace(hour=int(hours), minute=int(minutes), second=0, microsecond=0)


def is_slot_orderable(slot: str, now: datetime, settings: Settings | None = None) -> bool:
    """La franja existe y empieza al menos ``MIN_LEAD_MINUTES`` después de ``now`` (S5)."""
    s = settings or load_settings()
    if not SLOT_RE.match(slot or "") or slot not in all_slots(s):
        return False
    return slot_start(slot, now) >= now + timedelta(minutes=s.min_lead_minutes)


def build_availability(
    now: datetime,
    slot_counts: Mapping[str, int],
    stock: Mapping[str, int],
    settings: Settings | None = None,
) -> dict:
    """Cuerpo de ``GET /api/availability``.

    ``available`` = franja a ≥ 30 min **y** ``remaining > 0`` **y** tienda abierta.
    """
    s = settings or load_settings()
    store_open = is_store_open(now, s)
    slots = []
    for slot in all_slots(s):
        remaining = max(s.slot_capacity - int(slot_counts.get(slot, 0)), 0)
        available = store_open and remaining > 0 and is_slot_orderable(slot, now, s)
        slots.append({"slot": slot, "remaining": remaining, "available": available})
    return {
        "date": today(now),
        "storeOpen": store_open,
        "openTime": s.open_time,
        "closeTime": s.close_time,
        "slots": slots,
        "stock": {pid: int(qty) for pid, qty in sorted(stock.items())},
    }
