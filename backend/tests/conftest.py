"""Fixtures compartidas: variables de entorno del contrato 04, reloj fijo, eventos de API Gateway y
tablas DynamoDB simuladas con moto IDÉNTICAS al contrato 03 (claves, GSI y TTL)."""

import json
from collections.abc import Callable, Iterator
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import boto3
import pytest
from moto import mock_aws

from app import aws, clock

TEST_ENV = {
    "ENV": "test",
    "LOG_LEVEL": "DEBUG",
    "PRODUCTS_TABLE": "pdc-test-products",
    "ORDERS_TABLE": "pdc-test-orders",
    "ORDERS_BY_DATE_INDEX": "byDate",
    "SLOTS_TABLE": "pdc-test-slots",
    "IDEMPOTENCY_TABLE": "pdc-test-idempotency",
    "ASSETS_BUCKET": "pdc-test-assets",
    "ASSETS_BASE_URL": "https://cdn.example.test",
    # Credenciales FICTICIAS para moto: nunca se habla con AWS real.
    "AWS_DEFAULT_REGION": "us-east-1",
    "AWS_ACCESS_KEY_ID": "testing",
    "AWS_SECRET_ACCESS_KEY": "testing",
}


@pytest.fixture(autouse=True)
def app_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    for key, value in TEST_ENV.items():
        monkeypatch.setenv(key, value)
    return TEST_ENV


@pytest.fixture
def set_now(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], datetime]:
    """Fija ``app.clock.now`` a una hora de Bogotá: ``set_now("2026-11-27T09:45")``."""

    def _set(value: str) -> datetime:
        fixed = datetime.fromisoformat(value).replace(tzinfo=clock.BOGOTA)
        monkeypatch.setattr(clock, "now", lambda: fixed)
        return fixed

    return _set


@pytest.fixture
def lambda_context() -> SimpleNamespace:
    return SimpleNamespace(aws_request_id="req-test-0001", function_name="pdc-test-fn")


@pytest.fixture
def make_event() -> Callable[..., dict[str, Any]]:
    """Construye un evento HTTP API (payload 2.0)."""

    def _make(
        route_key: str,
        *,
        body: Any = None,
        headers: dict[str, str] | None = None,
        path: dict[str, str] | None = None,
        query: dict[str, str] | None = None,
        username: str | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "version": "2.0",
            "routeKey": route_key,
            "headers": {k.lower(): v for k, v in (headers or {}).items()},
            "isBase64Encoded": False,
            "requestContext": {"requestId": "apigw-req-1"},
        }
        if body is not None:
            event["body"] = body if isinstance(body, str) else json.dumps(body)
        if path:
            event["pathParameters"] = path
        if query:
            event["queryStringParameters"] = query
        if username:
            event["requestContext"]["authorizer"] = {"jwt": {"claims": {"username": username}}}
        return event

    return _make


def read_logs(captured: str) -> list[dict[str, Any]]:
    """Convierte la salida capturada (una línea JSON por evento) en dicts."""
    records = [json.loads(line) for line in captured.splitlines() if line.startswith("{")]
    return [record for record in records if "_aws" not in record]  # las líneas EMF no son logs


def body_of(response: dict[str, Any]) -> Any:
    return json.loads(response["body"]) if response.get("body") else None


# --- DynamoDB simulado (contrato 03) ------------------------------------------------------------


def _create_tables(ddb: Any) -> None:
    on_demand = {"BillingMode": "PAY_PER_REQUEST"}
    ddb.create_table(
        TableName=TEST_ENV["PRODUCTS_TABLE"],
        KeySchema=[{"AttributeName": "productId", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "productId", "AttributeType": "S"}],
        **on_demand,
    )
    ddb.create_table(
        TableName=TEST_ENV["ORDERS_TABLE"],
        KeySchema=[{"AttributeName": "orderId", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "orderId", "AttributeType": "S"},
            {"AttributeName": "pickupDate", "AttributeType": "S"},
            {"AttributeName": "slotKey", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": TEST_ENV["ORDERS_BY_DATE_INDEX"],
                "KeySchema": [
                    {"AttributeName": "pickupDate", "KeyType": "HASH"},
                    {"AttributeName": "slotKey", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        **on_demand,
    )
    ddb.create_table(
        TableName=TEST_ENV["SLOTS_TABLE"],
        KeySchema=[
            {"AttributeName": "date", "KeyType": "HASH"},
            {"AttributeName": "slot", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "date", "AttributeType": "S"},
            {"AttributeName": "slot", "AttributeType": "S"},
        ],
        **on_demand,
    )
    ddb.create_table(
        TableName=TEST_ENV["IDEMPOTENCY_TABLE"],
        KeySchema=[{"AttributeName": "idempotencyKey", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "idempotencyKey", "AttributeType": "S"}],
        **on_demand,
    )
    for name in ("SLOTS_TABLE", "IDEMPOTENCY_TABLE"):
        ddb.update_time_to_live(
            TableName=TEST_ENV[name],
            TimeToLiveSpecification={"Enabled": True, "AttributeName": "expiresAt"},
        )


@pytest.fixture
def ddb(app_env: dict[str, str]) -> Iterator[Any]:
    """Activa moto, crea las 4 tablas y devuelve el *resource* de DynamoDB."""
    aws.reset()
    with mock_aws():
        _create_tables(boto3.client("dynamodb", region_name="us-east-1"))
        yield boto3.resource("dynamodb", region_name="us-east-1")
    aws.reset()


SAMPLE_PRODUCTS = [
    {"productId": "p-croissant", "name": "Croissant", "category": "Hojaldres", "price": 4500, "stock": 42},
    {"productId": "p-pan-queso", "name": "Pan de queso", "category": "Panes", "price": 1500, "stock": 0},
    {"productId": "p-almojabana", "name": "Almojábana", "category": "Panes", "price": 2500, "stock": 30},
    {
        "productId": "p-viejo",
        "name": "Pan viejo",
        "category": "Panes",
        "price": 900,
        "stock": 5,
        "active": False,
    },
]


@pytest.fixture
def products(ddb: Any) -> dict[str, dict[str, Any]]:
    """Carga productos de ejemplo (datos ficticios). ``p-viejo`` está inactivo."""
    table = ddb.Table(TEST_ENV["PRODUCTS_TABLE"])
    loaded = {}
    for base in SAMPLE_PRODUCTS:
        item = {
            "description": f"{base['name']} de prueba",
            "dailyProduction": 60,
            "active": True,
            "updatedAt": "2026-11-27T05:30:00-05:00",
            **base,
        }
        table.put_item(Item=item)
        loaded[item["productId"]] = item
    return loaded


def get_item(ddb: Any, env_table: str, **key: Any) -> dict[str, Any] | None:
    return ddb.Table(TEST_ENV[env_table]).get_item(Key=key).get("Item")


def stock_of(ddb: Any, product_id: str) -> int:
    return int(get_item(ddb, "PRODUCTS_TABLE", productId=product_id)["stock"])


def slot_count(ddb: Any, date: str, slot: str) -> int:
    item = get_item(ddb, "SLOTS_TABLE", date=date, slot=slot)
    return int(item["count"]) if item else 0


def as_plain(value: Any) -> Any:
    """Convierte los Decimal de DynamoDB a int para comparar fácil."""
    if isinstance(value, Decimal):
        return int(value)
    if isinstance(value, list):
        return [as_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: as_plain(v) for k, v in value.items()}
    return value


@pytest.fixture
def assets_bucket(ddb: Any) -> Any:
    """Bucket de assets simulado (dentro del mismo ``mock_aws`` de ``ddb``). Devuelve el cliente S3."""
    client = boto3.client("s3", region_name="us-east-1")
    client.create_bucket(Bucket=TEST_ENV["ASSETS_BUCKET"])
    return client


def read_catalog(s3_client: Any) -> dict[str, Any]:
    obj = s3_client.get_object(Bucket=TEST_ENV["ASSETS_BUCKET"], Key="assets/catalog/catalog.json")
    return {
        "body": json.loads(obj["Body"].read()),
        "ContentType": obj["ContentType"],
        "CacheControl": obj.get("CacheControl"),
    }


@pytest.fixture
def place_order(products: Any, make_event: Callable[..., dict[str, Any]], lambda_context: Any, set_now: Any):
    """Crea pedidos REALES con el handler create-order: ``place_order("10:00", [("p-croissant", 2)])``."""
    import uuid

    from app.handlers import create_order

    def _place(slot: str = "10:00", lines: Any = (("p-croissant", 1),), at: str = "2026-11-27T08:00") -> dict:
        set_now(at)
        body = {
            "customer": {"name": "Cliente Prueba", "phone": "3009998877"},
            "pickupSlot": slot,
            "items": [{"productId": pid, "quantity": qty} for pid, qty in lines],
            "dataConsent": True,
        }
        event = make_event("POST /api/orders", body=body, headers={"Idempotency-Key": str(uuid.uuid4())})
        response = create_order.handler(event, lambda_context)
        assert response["statusCode"] == 201, response
        return json.loads(response["body"])

    return _place
