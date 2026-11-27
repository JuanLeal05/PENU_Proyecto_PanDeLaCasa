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
    # Lectura consistente: publish_catalog() escanea justo después de escribir un producto y una
    # lectura eventual podría publicar el precio viejo. En ~40 ítems el costo extra es despreciable.
    kwargs.setdefault("ConsistentRead", True)
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


def update_fields(product_id: str, changes: dict[str, Any], updated_at: str) -> dict[str, Any] | None:
    """``SET`` parcial con condición de existencia. Devuelve el ítem nuevo o ``None`` si no existe."""
    values: dict[str, Any] = {":updatedAt": updated_at}
    names: dict[str, str] = {"#updatedAt": "updatedAt"}
    sets = ["#updatedAt = :updatedAt"]
    for index, (field, value) in enumerate(changes.items()):
        names[f"#f{index}"] = field
        values[f":v{index}"] = value
        sets.append(f"#f{index} = :v{index}")
    table = aws.products_table()
    try:
        response = table.update_item(
            Key={"productId": product_id},
            UpdateExpression="SET " + ", ".join(sets),
            ConditionExpression="attribute_exists(productId)",
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return None
    return response["Attributes"]


def reset_stock(product_id: str, updated_at: str) -> bool:
    """``stock = dailyProduction`` (job de las 05:30). ``False`` si el producto ya no existe."""
    table = aws.products_table()
    try:
        table.update_item(
            Key={"productId": product_id},
            UpdateExpression="SET #stock = dailyProduction, updatedAt = :now",
            ConditionExpression="attribute_exists(productId) AND attribute_exists(dailyProduction)",
            ExpressionAttributeNames={"#stock": "stock"},
            ExpressionAttributeValues={":now": updated_at},
        )
    except table.meta.client.exceptions.ConditionalCheckFailedException:
        return False
    return True
