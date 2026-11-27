import re

import pytest

from app import clock
from app.config import ConfigError, load_settings, require_env


def test_defaults_del_contrato(monkeypatch):
    for name in ["ENV", "LOG_LEVEL", "SLOT_CAPACITY", "OPEN_TIME", "FIRST_SLOT", "MAX_UNITS_PER_ORDER"]:
        monkeypatch.delenv(name, raising=False)
    s = load_settings()
    assert (s.env, s.log_level, s.slot_capacity) == ("dev", "INFO", 10)
    assert (s.open_time, s.close_time, s.first_slot, s.last_slot) == ("06:00", "18:00", "07:00", "17:30")
    assert (s.slot_minutes, s.min_lead_minutes) == (30, 30)
    assert (s.max_units_per_order, s.max_lines_per_order) == (20, 10)
    assert s.orders_by_date_index == "byDate"


def test_lee_variables_de_entorno(monkeypatch):
    monkeypatch.setenv("SLOT_CAPACITY", "12")
    monkeypatch.setenv("ASSETS_BASE_URL", "https://cdn.example.test/")
    s = load_settings()
    assert s.slot_capacity == 12
    assert s.assets_base_url == "https://cdn.example.test"


def test_tablas_son_obligatorias(monkeypatch):
    assert require_env("ORDERS_TABLE") == "pdc-test-orders"
    monkeypatch.delenv("ORDERS_TABLE")
    with pytest.raises(ConfigError, match="ORDERS_TABLE"):
        require_env("ORDERS_TABLE")


def test_reloj_en_bogota():
    now = clock.now()
    assert now.utcoffset().total_seconds() == -5 * 3600
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d-05:00", clock.iso(now))


def test_reloj_reemplazable(set_now):
    set_now("2026-11-27T09:15")
    assert clock.iso(clock.now()) == "2026-11-27T09:15:00-05:00"
