"""Tabla ``pdc-<env>-idempotency`` (contrato 03 §4). TTL de 24 h en ``expiresAt``."""

from datetime import datetime, timedelta
from typing import Any

from app import aws

IDEMPOTENCY_TTL = timedelta(hours=24)


def get(idempotency_key: str) -> dict[str, Any] | None:
    """Devuelve la clave guardada si existe y no ha vencido.

    El TTL de DynamoDB borra con retraso (hasta horas), así que también filtramos por ``expiresAt``.
    """
    item = (
        aws.idempotency_table()
        .get_item(Key={"idempotencyKey": idempotency_key}, ConsistentRead=True)
        .get("Item")
    )
    return item


def is_expired(item: dict[str, Any], now: datetime) -> bool:
    return int(item.get("expiresAt", 0)) <= int(now.timestamp())


def build_item(
    idempotency_key: str, order_id: str, request_hash: str, response_json: str, now: datetime
) -> dict[str, Any]:
    return {
        "idempotencyKey": idempotency_key,
        "orderId": order_id,
        "requestHash": request_hash,
        "response": response_json,
        "expiresAt": int((now + IDEMPOTENCY_TTL).timestamp()),
    }
