"""Tabla ``pdc-<env>-slots`` (contrato 03 §3). El ítem de una franja no se precrea."""

from datetime import datetime, timedelta

from boto3.dynamodb.conditions import Key

from app import aws
from app.clock import BOGOTA

SLOT_TTL_DAYS = 7


def counts_for(date: str) -> dict[str, int]:
    """``{slot: count}`` del día (``Query`` con ``date = :d``; el builder escapa la palabra reservada)."""
    table = aws.slots_table()
    kwargs = {"KeyConditionExpression": Key("date").eq(date), "ConsistentRead": True}
    counts: dict[str, int] = {}
    while True:
        response = table.query(**kwargs)
        for item in response.get("Items", []):
            counts[item["slot"]] = int(item.get("count", 0))
        if "LastEvaluatedKey" not in response:
            return counts
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def expires_at(date: str) -> int:
    """TTL: medianoche de Bogotá de ``date`` + 7 días, en epoch segundos."""
    midnight = datetime.fromisoformat(date).replace(tzinfo=BOGOTA)
    return int((midnight + timedelta(days=SLOT_TTL_DAYS)).timestamp())
