"""Tabla ``pdc-<env>-orders`` (contrato 03 §2)."""

from typing import Any

from boto3.dynamodb.conditions import Key

from app import aws
from app.config import load_settings


def get(order_id: str) -> dict[str, Any] | None:
    return aws.orders_table().get_item(Key={"orderId": order_id}, ConsistentRead=True).get("Item")


def query_by_date(pickup_date: str) -> list[dict[str, Any]]:
    """Pedidos del día por el GSI ``byDate``, ordenados por ``slotKey`` (franja y luego ``createdAt``)."""
    table = aws.orders_table()
    kwargs: dict[str, Any] = {
        "IndexName": load_settings().orders_by_date_index,
        "KeyConditionExpression": Key("pickupDate").eq(pickup_date),
        "ScanIndexForward": True,
    }
    orders: list[dict[str, Any]] = []
    while True:
        response = table.query(**kwargs)
        orders.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            return orders
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
