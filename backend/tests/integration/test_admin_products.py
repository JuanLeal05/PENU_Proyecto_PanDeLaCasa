"""``admin-products`` contra DynamoDB y S3 simulados."""

from urllib.parse import parse_qs, urlsplit

import pytest

from app.handlers import admin_products
from conftest import TEST_ENV, body_of, read_catalog, read_logs, stock_of


@pytest.fixture
def call(make_event, lambda_context, ddb, products, assets_bucket, set_now):
    set_now("2026-11-27T07:00")

    def _call(route, body=None, path=None):
        event = make_event(route, body=body, path=path, username="maria")
        return admin_products.handler(event, lambda_context)

    return _call


def code(resp):
    return body_of(resp)["error"]["code"]


def test_list_incluye_inactivos(call):
    resp = call("GET /api/admin/products")
    assert resp["statusCode"] == 200
    items = body_of(resp)["products"]
    assert [p["productId"] for p in items] == ["p-croissant", "p-almojabana", "p-pan-queso", "p-viejo"]
    croissant = items[0]
    assert set(croissant) == {
        "productId",
        "name",
        "description",
        "category",
        "price",
        "imageUrl",
        "dailyProduction",
        "stock",
        "active",
        "updatedAt",
    }
    assert (croissant["stock"], croissant["dailyProduction"], croissant["active"]) == (42, 60, True)


def test_create_product(call, ddb, assets_bucket, capsys):
    resp = call(
        "POST /api/admin/products",
        {
            "name": "Pan de Yuca",
            "description": "Recién horneado",
            "category": "Panes",
            "price": 2000,
            "dailyProduction": 30,
            "active": True,
        },
    )
    assert resp["statusCode"] == 201
    product = body_of(resp)
    assert product["productId"] == "p-pan-de-yuca"
    assert product["stock"] == 30  # stock inicial = dailyProduction
    assert product["updatedAt"] == "2026-11-27T07:00:00-05:00"
    assert stock_of(ddb, "p-pan-de-yuca") == 30
    catalog = read_catalog(assets_bucket)["body"]
    assert "p-pan-de-yuca" in [p["productId"] for p in catalog["products"]]
    logs = read_logs(capsys.readouterr().out)
    assert {"product_created", "catalog_published"} <= {r["message"] for r in logs}


def test_create_slug_repetido_agrega_sufijo(call):
    body = {"name": "Croissant", "category": "Hojaldres", "price": 5000, "dailyProduction": 10}
    product = body_of(call("POST /api/admin/products", body))
    assert product["productId"].startswith("p-croissant-")
    assert len(product["productId"]) == len("p-croissant-") + 4


def test_create_invalido(call):
    resp = call("POST /api/admin/products", {"name": "X", "price": -1})
    assert (resp["statusCode"], code(resp)) == (400, "VALIDATION_ERROR")
    assert {"name", "price", "category", "dailyProduction"} <= set(
        body_of(resp)["error"]["details"]["fields"]
    )


def test_update_product_y_republica(call, assets_bucket):
    resp = call(
        "PUT /api/admin/products/{productId}",
        {"price": 5200, "name": "Croissant grande"},
        {"productId": "p-croissant"},
    )
    assert resp["statusCode"] == 200
    product = body_of(resp)
    assert (product["price"], product["name"], product["stock"]) == (5200, "Croissant grande", 42)
    catalog = read_catalog(assets_bucket)["body"]
    assert next(p for p in catalog["products"] if p["productId"] == "p-croissant")["price"] == 5200


def test_update_image_key(call, assets_bucket):
    key = "assets/images/p-croissant/7d1e9a2b.webp"
    product = body_of(
        call("PUT /api/admin/products/{productId}", {"imageKey": key}, {"productId": "p-croissant"})
    )
    assert product["imageUrl"] == f"https://cdn.example.test/{key}"
    catalog = read_catalog(assets_bucket)["body"]
    assert catalog["products"][0]["imageUrl"] == f"https://cdn.example.test/{key}"


def test_update_inexistente(call):
    resp = call("PUT /api/admin/products/{productId}", {"price": 1}, {"productId": "p-nada"})
    assert (resp["statusCode"], code(resp)) == (404, "NOT_FOUND")


def test_reactivar_producto(call, assets_bucket):
    call("PUT /api/admin/products/{productId}", {"active": True}, {"productId": "p-viejo"})
    ids = [p["productId"] for p in read_catalog(assets_bucket)["body"]["products"]]
    assert "p-viejo" in ids


def test_delete_es_logico(call, ddb, assets_bucket):
    resp = call("DELETE /api/admin/products/{productId}", path={"productId": "p-croissant"})
    assert resp["statusCode"] == 204
    assert "body" not in resp
    item = ddb.Table(TEST_ENV["PRODUCTS_TABLE"]).get_item(Key={"productId": "p-croissant"})["Item"]
    assert item["active"] is False
    ids = [p["productId"] for p in read_catalog(assets_bucket)["body"]["products"]]
    assert "p-croissant" not in ids


def test_delete_inexistente(call):
    resp = call("DELETE /api/admin/products/{productId}", path={"productId": "p-nada"})
    assert (resp["statusCode"], code(resp)) == (404, "NOT_FOUND")


def test_presigned_url(call):
    resp = call(
        "POST /api/admin/products/{productId}/image",
        {"contentType": "image/webp"},
        {"productId": "p-croissant"},
    )
    assert resp["statusCode"] == 200
    body = body_of(resp)
    assert body["expiresIn"] == 300
    assert body["imageKey"].startswith("assets/images/p-croissant/")
    assert body["imageKey"].endswith(".webp")
    url = urlsplit(body["uploadUrl"])
    assert TEST_ENV["ASSETS_BUCKET"] in url.netloc + url.path
    assert url.path.endswith(body["imageKey"])
    query = parse_qs(url.query)
    assert query.get("X-Amz-Expires") == ["300"] or "Expires" in query


def test_presigned_url_rechaza_gif(call):
    resp = call(
        "POST /api/admin/products/{productId}/image",
        {"contentType": "image/gif"},
        {"productId": "p-croissant"},
    )
    assert (resp["statusCode"], code(resp)) == (400, "VALIDATION_ERROR")


def test_presigned_url_producto_inexistente(call):
    resp = call(
        "POST /api/admin/products/{productId}/image", {"contentType": "image/png"}, {"productId": "p-nada"}
    )
    assert (resp["statusCode"], code(resp)) == (404, "NOT_FOUND")


def test_inventory(call, ddb):
    resp = call(
        "PUT /api/admin/inventory",
        {
            "items": [
                {"productId": "p-croissant", "stock": 60, "dailyProduction": 70},
                {"productId": "p-pan-queso", "stock": 5},
            ]
        },
    )
    assert resp["statusCode"] == 200
    products = {p["productId"]: p for p in body_of(resp)["products"]}
    assert (products["p-croissant"]["stock"], products["p-croissant"]["dailyProduction"]) == (60, 70)
    assert (products["p-pan-queso"]["stock"], products["p-pan-queso"]["dailyProduction"]) == (5, 60)
    assert stock_of(ddb, "p-pan-queso") == 5


def test_inventory_con_inexistente_no_escribe_nada(call, ddb):
    resp = call(
        "PUT /api/admin/inventory",
        {
            "items": [
                {"productId": "p-croissant", "stock": 1},
                {"productId": "p-nada", "stock": 1},
            ]
        },
    )
    assert (resp["statusCode"], code(resp)) == (404, "NOT_FOUND")
    assert body_of(resp)["error"]["details"]["productIds"] == ["p-nada"]
    assert stock_of(ddb, "p-croissant") == 42


def test_inventory_invalido(call):
    resp = call("PUT /api/admin/inventory", {"items": [{"productId": "p-croissant", "stock": -5}]})
    assert (resp["statusCode"], code(resp)) == (400, "VALIDATION_ERROR")
