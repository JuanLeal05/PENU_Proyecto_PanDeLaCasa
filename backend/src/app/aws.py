"""Recursos de boto3 creados UNA vez por entorno de ejecución (fuera del handler, perezosos).

Reutilizarlos entre invocaciones calientes evita repetir el handshake TLS y reduce la latencia.
Los nombres de tablas y buckets son obligatorios (``require_env``).
"""

import functools
from typing import Any

import boto3
from botocore.config import Config

from app.config import require_env

_BOTO_CONFIG = Config(
    connect_timeout=2,
    read_timeout=5,
    retries={"max_attempts": 3, "mode": "standard"},
)


@functools.cache
def dynamodb() -> Any:
    return boto3.resource("dynamodb", config=_BOTO_CONFIG)


@functools.cache
def s3() -> Any:
    return boto3.client("s3", config=_BOTO_CONFIG)


def ddb_client() -> Any:
    """Cliente del *resource*: acepta tipos Python normales (incluido ``transact_write_items``)."""
    return dynamodb().meta.client


def table(env_var: str) -> Any:
    return dynamodb().Table(require_env(env_var))


def products_table() -> Any:
    return table("PRODUCTS_TABLE")


def orders_table() -> Any:
    return table("ORDERS_TABLE")


def slots_table() -> Any:
    return table("SLOTS_TABLE")


def idempotency_table() -> Any:
    return table("IDEMPOTENCY_TABLE")


def reset() -> None:
    """Solo para tests: olvida los recursos cacheados."""
    dynamodb.cache_clear()
    s3.cache_clear()
