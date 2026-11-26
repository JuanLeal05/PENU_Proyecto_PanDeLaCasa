from datetime import datetime

import pytest

from app.clock import BOGOTA
from app.domain.schedule import (
    all_slots,
    build_availability,
    is_slot_orderable,
    is_store_open,
    today,
)


def at(hhmm: str, seconds: int = 0) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(2026, 11, 27, h, m, seconds, tzinfo=BOGOTA)


def test_slots_generation():
    slots = all_slots()
    assert len(slots) == 22
    assert slots[0] == "07:00"
    assert slots[1] == "07:30"
    assert slots[-1] == "17:30"


def test_lead_time():
    now = at("09:45")
    assert not is_slot_orderable("10:00", now)
    assert is_slot_orderable("10:30", now)


def test_lead_time_borde_exacto():
    assert is_slot_orderable("10:00", at("09:30"))
    assert not is_slot_orderable("10:00", at("09:30", 1))


@pytest.mark.parametrize("slot", ["06:30", "18:00", "10:15", "7:00", "25:00", "", "abc"])
def test_franjas_inexistentes(slot):
    assert not is_slot_orderable(slot, at("06:00"))


@pytest.mark.parametrize(
    ("hhmm", "open_"),
    [("05:59", False), ("06:00", True), ("12:00", True), ("17:59", True), ("18:00", False), ("18:05", False)],
)
def test_store_closed(hhmm, open_):
    assert is_store_open(at(hhmm)) is open_


def test_today():
    assert today(at("23:59")) == "2026-11-27"


def test_build_availability():
    body = build_availability(at("09:45"), {"07:00": 10, "10:30": 3, "11:00": 10}, {"p-b": 0, "p-a": 42})
    assert body["date"] == "2026-11-27"
    assert body["storeOpen"] is True
    assert (body["openTime"], body["closeTime"]) == ("06:00", "18:00")
    slots = {s["slot"]: s for s in body["slots"]}
    assert len(slots) == 22
    assert slots["07:00"] == {"slot": "07:00", "remaining": 0, "available": False}
    assert slots["10:00"] == {"slot": "10:00", "remaining": 10, "available": False}  # < 30 min
    assert slots["10:30"] == {"slot": "10:30", "remaining": 7, "available": True}
    assert slots["11:00"]["available"] is False  # llena
    assert body["stock"] == {"p-a": 42, "p-b": 0}


def test_build_availability_tienda_cerrada():
    body = build_availability(at("05:00"), {}, {})
    assert body["storeOpen"] is False
    assert not any(s["available"] for s in body["slots"])
    assert all(s["remaining"] == 10 for s in body["slots"])


def test_remaining_nunca_negativo():
    body = build_availability(at("06:00"), {"08:00": 12}, {})
    assert next(s for s in body["slots"] if s["slot"] == "08:00")["remaining"] == 0
