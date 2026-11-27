import pytest

from app.domain import products as p
from app.http import ApiError

PREFIX = "assets/images/"


def fields_of(fn, *args):
    with pytest.raises(ApiError) as info:
        fn(*args)
    assert (info.value.status, info.value.code) == (400, "VALIDATION_ERROR")
    return info.value.details["fields"]


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Croissant", "croissant"),
        ("Pan de Queso", "pan-de-queso"),
        ("Almojábana   Ñapa!!", "almojabana-napa"),
        ("  --Torta (porción)--  ", "torta-porcion"),
        ("¡¡¡", "producto"),
        ("x" * 60, "x" * 40),
    ],
)
def test_slugify(name, slug):
    assert p.slugify(name) == slug
    assert p.product_id_for(name) == f"p-{slug}"


def test_create_valido_con_defaults():
    data = p.validate_product_create(
        {"name": " Croissant ", "category": "Hojaldres", "price": 4500, "dailyProduction": 60}
    )
    assert data == {
        "name": "Croissant",
        "description": "",
        "category": "Hojaldres",
        "price": 4500,
        "dailyProduction": 60,
        "active": True,
    }


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"category": "Panes", "price": 1, "dailyProduction": 1}, "name"),
        ({"name": "Pan", "category": "Panes", "price": 0, "dailyProduction": 1}, "price"),
        ({"name": "Pan", "category": "Panes", "price": 99.5, "dailyProduction": 1}, "price"),
        ({"name": "Pan", "category": "Panes", "price": 1, "dailyProduction": -1}, "dailyProduction"),
        ({"name": "Pan", "category": "Panes", "price": 1, "dailyProduction": 1, "active": "sí"}, "active"),
        ({"name": "Pan", "category": "Panes", "price": 1, "dailyProduction": 1, "stock": 5}, "stock"),
        ({"name": "Pan", "price": 1, "dailyProduction": 1}, "category"),
    ],
)
def test_create_invalido(body, field):
    assert field in fields_of(p.validate_product_create, body)


def test_update_parcial():
    assert p.validate_product_update({"price": 5000, "active": False}, "p-croissant", PREFIX) == {
        "price": 5000,
        "active": False,
    }
    key = "assets/images/p-croissant/7d1e9a2b.webp"
    assert p.validate_product_update({"imageKey": key}, "p-croissant", PREFIX) == {"imageKey": key}


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({}, "body"),
        ({"imageKey": "assets/images/p-otro/abc.webp"}, "imageKey"),
        ({"imageKey": "assets/images/p-croissant/../x.webp"}, "imageKey"),
        ({"imageKey": "assets/images/p-croissant/abc.gif"}, "imageKey"),
        ({"imageKey": "assets/catalog/catalog.json"}, "imageKey"),
        ({"stock": 3}, "stock"),
        ({"productId": "p-x"}, "productId"),
        ({"name": "x"}, "name"),
    ],
)
def test_update_invalido(body, field):
    assert field in fields_of(p.validate_product_update, body, "p-croissant", PREFIX)


@pytest.mark.parametrize(
    ("ctype", "ext"), [("image/jpeg", "jpg"), ("image/png", "png"), ("image/webp", "webp")]
)
def test_image_request(ctype, ext):
    assert p.validate_image_request({"contentType": ctype}) == (ctype, ext)


@pytest.mark.parametrize("ctype", ["image/gif", "", None, "text/html"])
def test_image_request_invalido(ctype):
    assert fields_of(p.validate_image_request, {"contentType": ctype}) == ["contentType"]


def test_inventory():
    items = p.validate_inventory(
        {
            "items": [
                {"productId": "p-croissant", "stock": 60, "dailyProduction": 60},
                {"productId": "p-pan-queso", "stock": 0},
            ]
        }
    )
    assert items == [
        {"productId": "p-croissant", "stock": 60, "dailyProduction": 60},
        {"productId": "p-pan-queso", "stock": 0},
    ]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"items": []}, "items"),
        ({}, "items"),
        ({"items": [{"productId": "p-a", "stock": -1}]}, "items[0].stock"),
        ({"items": [{"productId": "p-a"}]}, "items[0].stock"),
        ({"items": [{"productId": "X", "stock": 1}]}, "items[0].productId"),
        ({"items": [{"productId": "p-a", "stock": 1, "dailyProduction": 1.5}]}, "items[0].dailyProduction"),
    ],
)
def test_inventory_invalido(body, field):
    assert field in fields_of(p.validate_inventory, body)


def test_to_product():
    item = {
        "productId": "p-a",
        "name": "A",
        "description": "d",
        "category": "Panes",
        "price": 100,
        "dailyProduction": 5,
        "stock": 2,
        "active": True,
        "updatedAt": "t",
        "imageKey": "assets/images/p-a/x.webp",
    }
    view = p.to_product(item, "https://cdn.example.test")
    assert view["imageUrl"] == "https://cdn.example.test/assets/images/p-a/x.webp"
    assert view["stock"] == 2
    assert p.to_product({**item, "imageKey": None}, "https://cdn.example.test")["imageUrl"] is None
