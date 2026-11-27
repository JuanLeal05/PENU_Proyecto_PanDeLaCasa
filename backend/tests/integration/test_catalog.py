"""``publish_catalog`` contra S3 y DynamoDB simulados."""

from app.catalog import publish_catalog
from conftest import TEST_ENV, read_catalog


def test_publish_catalog(ddb, products, assets_bucket, set_now):
    set_now("2026-11-27T06:00")
    ddb.Table(TEST_ENV["PRODUCTS_TABLE"]).update_item(
        Key={"productId": "p-croissant"},
        UpdateExpression="SET imageKey = :k",
        ExpressionAttributeValues={":k": "assets/images/p-croissant/7d1e.webp"},
    )
    returned = publish_catalog()
    stored = read_catalog(assets_bucket)
    catalog = stored["body"]

    assert catalog == returned
    assert stored["ContentType"] == "application/json"
    assert stored["CacheControl"] == "max-age=60"
    assert catalog["generatedAt"] == "2026-11-27T06:00:00-05:00"
    assert catalog["currency"] == "COP"
    ids = [p["productId"] for p in catalog["products"]]
    assert ids == ["p-croissant", "p-almojabana", "p-pan-queso"]  # Hojaldres < Panes; por nombre
    assert "p-viejo" not in ids  # inactivo
    for product in catalog["products"]:
        assert set(product) == {"productId", "name", "description", "category", "price", "imageUrl"}
        assert "stock" not in product
    croissant = catalog["products"][0]
    assert croissant["imageUrl"] == "https://cdn.example.test/assets/images/p-croissant/7d1e.webp"
    assert catalog["products"][1]["imageUrl"] is None
