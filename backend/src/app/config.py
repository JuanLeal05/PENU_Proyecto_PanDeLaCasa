"""Configuración leída de las variables de entorno (contrato 04 §2).

Regla del contrato: si falta una variable se usa el default del contrato, EXCEPTO los nombres de
tablas y buckets, que son obligatorios (``require_env`` falla en cuanto el handler los necesita).
"""

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """Falta una variable de entorno obligatoria."""


def require_env(name: str) -> str:
    """Devuelve una variable obligatoria (tabla o bucket) o lanza ``ConfigError``."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Falta la variable de entorno obligatoria {name}")
    return value


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _str(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip()
    return raw or default


@dataclass(frozen=True)
class Settings:
    env: str
    log_level: str
    slot_capacity: int
    open_time: str
    close_time: str
    first_slot: str
    last_slot: str
    slot_minutes: int
    min_lead_minutes: int
    max_units_per_order: int
    max_lines_per_order: int
    orders_by_date_index: str
    catalog_key: str
    images_prefix: str
    assets_base_url: str


def load_settings() -> Settings:
    """Lee la configuración no sensible con los defaults del contrato 04 §2."""
    return Settings(
        env=_str("ENV", "dev"),
        log_level=_str("LOG_LEVEL", "INFO").upper(),
        slot_capacity=_int("SLOT_CAPACITY", 10),
        open_time=_str("OPEN_TIME", "06:00"),
        close_time=_str("CLOSE_TIME", "18:00"),
        first_slot=_str("FIRST_SLOT", "07:00"),
        last_slot=_str("LAST_SLOT", "17:30"),
        slot_minutes=_int("SLOT_MINUTES", 30),
        min_lead_minutes=_int("MIN_LEAD_MINUTES", 30),
        max_units_per_order=_int("MAX_UNITS_PER_ORDER", 20),
        max_lines_per_order=_int("MAX_LINES_PER_ORDER", 10),
        orders_by_date_index=_str("ORDERS_BY_DATE_INDEX", "byDate"),
        catalog_key=_str("CATALOG_KEY", "assets/catalog/catalog.json"),
        images_prefix=_str("IMAGES_PREFIX", "assets/images/"),
        assets_base_url=_str("ASSETS_BASE_URL", "").rstrip("/"),
    )
