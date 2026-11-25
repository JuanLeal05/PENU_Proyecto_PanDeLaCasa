"""Transacciones de DynamoDB: el corazón de la concurrencia (contrato 01 §3).

No hay locks ni colas: la atomicidad y las condiciones de ``TransactWriteItems`` evitan la
sobreventa del último cupo y del último pan, y la idempotencia evita pedidos duplicados.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from botocore.exceptions import ClientError

from app import aws
from app.config import load_settings, require_env
from app.repositories.slots_repo import expires_at

CONDITION_FAILED = "ConditionalCheckFailed"


class TransactionConflict(Exception):
    """Base de los fallos de condición que el handler traduce a errores de negocio."""


class SlotFullError(TransactionConflict):
    pass


class OutOfStockError(TransactionConflict):
    def __init__(self, product_ids: list[str]):
        super().__init__(", ".join(product_ids))
        self.product_ids = product_ids


class IdempotencyRaceError(TransactionConflict):
    """Otra petición con la misma ``Idempotency-Key`` ganó la carrera."""


class StaleStatusError(TransactionConflict):
    """El estado del pedido cambió entre la lectura y la escritura."""


def _reasons(err: ClientError) -> list[str]:
    return [reason.get("Code", "None") for reason in err.response.get("CancellationReasons", [])]


def _is_cancelled_tx(err: ClientError) -> bool:
    return err.response.get("Error", {}).get("Code") == "TransactionCanceledException"


def create_order_tx(
    order: Mapping[str, Any],
    lines: Sequence[tuple[str, int]],
    idempotency_item: Mapping[str, Any],
    now: datetime,
) -> None:
    """Reserva cupo + stock, inserta el pedido y la clave de idempotencia, todo o nada.

    El ORDEN de ``TransactItems`` importa para interpretar ``CancellationReasons``:
    ``[0]`` franja · ``[1..n]`` productos · ``[n+1]`` pedido · ``[n+2]`` idempotencia.
    """
    settings = load_settings()
    date, slot = order["pickupDate"], order["pickupSlot"]
    items: list[dict[str, Any]] = [
        {
            "Update": {
                "TableName": require_env("SLOTS_TABLE"),
                "Key": {"date": date, "slot": slot},
                "UpdateExpression": "ADD #count :one SET expiresAt = :exp",
                "ConditionExpression": "attribute_not_exists(#count) OR #count < :cap",
                "ExpressionAttributeNames": {"#count": "count"},
                "ExpressionAttributeValues": {
                    ":one": 1,
                    ":cap": settings.slot_capacity,
                    ":exp": expires_at(date),
                },
            }
        }
    ]
    for product_id, quantity in lines:
        items.append(
            {
                "Update": {
                    "TableName": require_env("PRODUCTS_TABLE"),
                    "Key": {"productId": product_id},
                    "UpdateExpression": "SET #stock = #stock - :q, updatedAt = :now",
                    "ConditionExpression": (
                        "attribute_exists(productId) AND #active = :true AND #stock >= :q"
                    ),
                    "ExpressionAttributeNames": {"#stock": "stock", "#active": "active"},
                    "ExpressionAttributeValues": {":q": quantity, ":true": True, ":now": order["createdAt"]},
                }
            }
        )
    items.append(
        {
            "Put": {
                "TableName": require_env("ORDERS_TABLE"),
                "Item": dict(order),
                "ConditionExpression": "attribute_not_exists(orderId)",
            }
        }
    )
    items.append(
        {
            "Put": {
                "TableName": require_env("IDEMPOTENCY_TABLE"),
                "Item": dict(idempotency_item),
                # Una clave vencida que el TTL aún no borró se puede reutilizar.
                "ConditionExpression": "attribute_not_exists(idempotencyKey) OR expiresAt <= :nowEpoch",
                "ExpressionAttributeValues": {":nowEpoch": int(now.timestamp())},
            }
        }
    )

    try:
        aws.ddb_client().transact_write_items(TransactItems=items)
    except ClientError as err:
        if not _is_cancelled_tx(err):
            raise
        reasons = _reasons(err)
        idem_index = len(items) - 1
        if len(reasons) == len(items):
            if reasons[idem_index] == CONDITION_FAILED:
                raise IdempotencyRaceError() from err
            if reasons[0] == CONDITION_FAILED:
                raise SlotFullError() from err
            failed = [
                pid
                for (pid, _), code in zip(lines, reasons[1 : idem_index - 1], strict=True)
                if code == CONDITION_FAILED
            ]
            if failed:
                raise OutOfStockError(failed) from err
        raise


def change_status_tx(
    order: Mapping[str, Any],
    new_status: str,
    history_entry: Mapping[str, Any],
    now_iso: str,
    restore_stock: bool,
) -> None:
    """Cambia el estado con condición sobre el estado actual.

    Si ``restore_stock`` (cancelación), en la MISMA transacción devuelve el stock de cada línea
    (sin condición de ``active``) y libera el cupo de la franja.
    Sin devolución de stock basta un ``UpdateItem`` condicional.
    """
    status_update = {
        "TableName": require_env("ORDERS_TABLE"),
        "Key": {"orderId": order["orderId"]},
        "UpdateExpression": (
            "SET #status = :new, updatedAt = :now, statusHistory = list_append(statusHistory, :h)"
        ),
        "ConditionExpression": "#status = :current",
        "ExpressionAttributeNames": {"#status": "status"},
        "ExpressionAttributeValues": {
            ":new": new_status,
            ":current": order["status"],
            ":now": now_iso,
            ":h": [dict(history_entry)],
        },
    }

    try:
        if not restore_stock:
            aws.ddb_client().update_item(**status_update)
            return
        items: list[dict[str, Any]] = [{"Update": status_update}]
        for line in order.get("items", []):
            items.append(
                {
                    "Update": {
                        "TableName": require_env("PRODUCTS_TABLE"),
                        "Key": {"productId": line["productId"]},
                        "UpdateExpression": "SET #stock = #stock + :q, updatedAt = :now",
                        "ExpressionAttributeNames": {"#stock": "stock"},
                        "ExpressionAttributeValues": {":q": int(line["quantity"]), ":now": now_iso},
                    }
                }
            )
        items.append(
            {
                "Update": {
                    "TableName": require_env("SLOTS_TABLE"),
                    "Key": {"date": order["pickupDate"], "slot": order["pickupSlot"]},
                    "UpdateExpression": "ADD #count :minusOne",
                    "ConditionExpression": "#count > :zero",
                    "ExpressionAttributeNames": {"#count": "count"},
                    "ExpressionAttributeValues": {":minusOne": -1, ":zero": 0},
                }
            }
        )
        aws.ddb_client().transact_write_items(TransactItems=items)
    except ClientError as err:
        code = err.response.get("Error", {}).get("Code")
        if code == "ConditionalCheckFailedException":
            raise StaleStatusError() from err
        if _is_cancelled_tx(err) and _reasons(err)[:1] == [CONDITION_FAILED]:
            raise StaleStatusError() from err
        raise
