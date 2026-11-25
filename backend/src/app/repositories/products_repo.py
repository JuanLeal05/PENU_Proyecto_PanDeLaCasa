"""Tabla ``pdc-<env>-products`` (contrato 03 §1). Es chica (~40 ítems): un Scan es aceptable."""

from collections.abc import Iterable
from typing import Any

from boto3.dynamodb.conditions import Attr

from app import aws
from app.config import require_env


def get(product_id: str) -> dict[str, Any] | None:
    return aws.products_table().get_item(Key={"productId": product_id}).get("Item")


def batch_get(product_ids: Iterable[str]) -> dict[str, dict[str, Any]]:
    """``BatchGetItem`` (lectura consistente) → ``{productId: item}``. Reintenta ``UnprocessedKeys``."""
    ids = list(dict.fromkeys(product_ids))
    if not ids:
        return {}
    table_name = require_env("PRODUCTS_TABLE")
    request: dict[str, Any] = {
        table_name: {"Keys": [{"productId": pid} for pid in ids], "ConsistentRead": True}
    }
    found: dict[str, dict[str, Any]] = {}
    for _ in range(5):
        response = aws.dynamodb().batch_get_item(RequestItems=request)
        for item in response.get("Responses", {}).get(table_name, []):
            found[item["productId"]] = item
        request = response.get("UnprocessedKeys") or {}
        if not request:
            break
    return found


def _scan(**kwargs: Any) -> list[dict[str, Any]]:
    table = aws.products_table()
    items: list[dict[str, Any]] = []
    while True:
        response = table.scan(**kwargs)
        items.extend(response.get("Items", []))
        if "LastEvaluatedKey" not in response:
            return items
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def scan_all() -> list[dict[str, Any]]:
    return _scan()


def scan_active() -> list[dict[str, Any]]:
    return _scan(FilterExpression=Attr("active").eq(True))


def active_stock() -> dict[str, int]:
    """``{productId: stock}`` de los productos activos (para ``GET /api/availability``)."""
    items = _scan(
        FilterExpression=Attr("active").eq(True),
        ProjectionExpression="productId, #stock",
        ExpressionAttributeNames={"#stock": "stock"},
    )
    return {item["productId"]: int(item.get("stock", 0)) for item in items}


def put_if_absent(item: dict[str, Any]) -> bool:
    """Inserta el producto si no existe. Devuelve ``False`` si ya estaba (no lo pisa)."""
    table = aws.products_table()
    try:
        table.put_item(Item=item, ConditionExpression="attribute_not_exists(productId)")
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False
    return True
