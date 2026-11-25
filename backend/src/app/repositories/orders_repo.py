"""Tabla ``pdc-<env>-orders`` (contrato 03 §2)."""

from typing import Any

from app import aws


def get(order_id: str) -> dict[str, Any] | None:
    return aws.orders_table().get_item(Key={"orderId": order_id}, ConsistentRead=True).get("Item")
