"""Datos semilla y script de carga (contra moto; nunca contra AWS real)."""

import importlib.util
import json
from pathlib import Path

import pytest

from conftest import TEST_ENV, read_catalog

BACKEND = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND / "scripts" / "seed_products.py"
SEED = BACKEND / "seed" / "products.json"


@pytest.fixture(scope="module")
def seed_module():
    spec = importlib.util.spec_from_file_location("seed_products", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_json_es_valido(seed_module):
    products = seed_module.load_products(SEED)
    assert 10 <= len(products) <= 15
    assert all(p["productId"].startswith("p-") for p in products)
    assert all(isinstance(p["price"], int) and p["price"] > 0 for p in products)
    assert {"Panes", "Hojaldres", "Tortas", "Bebidas"} <= {p["category"] for p in products}


@pytest.mark.parametrize(
    ("data", "problem"),
    [
        ([], "lista no vacía"),
        ([{"productId": "p-a"}], "faltan"),
        (
            [
                {
                    **{"name": "x", "description": "", "category": "Panes"},
                    "productId": "P A",
                    "price": 1,
                    "dailyProduction": 1,
                    "active": True,
                }
            ],
            "productId inválido",
        ),
        (
            [
                {
                    "productId": "p-a",
                    "name": "x",
                    "description": "",
                    "category": "Panes",
                    "price": 99.5,
                    "dailyProduction": 1,
                    "active": True,
                }
            ],
            "price",
        ),
        (
            [
                {
                    "productId": "p-a",
                    "name": "x",
                    "description": "",
                    "category": "Panes",
                    "price": 1,
                    "dailyProduction": 1,
                    "active": "sí",
                }
            ],
            "active",
        ),
    ],
)
def test_seed_json_invalido(seed_module, tmp_path, data, problem):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(data))
    with pytest.raises(ValueError, match=problem):
        seed_module.load_products(bad)


def test_seed_es_idempotente(seed_module, ddb, capsys):
    table = ddb.Table(TEST_ENV["PRODUCTS_TABLE"])
    assert seed_module.main(["--table", TEST_ENV["PRODUCTS_TABLE"], "--file", str(SEED)]) == 0
    count = table.scan()["Count"]
    assert count == len(json.loads(SEED.read_text()))
    item = table.get_item(Key={"productId": "p-croissant"})["Item"]
    assert int(item["stock"]) == int(item["dailyProduction"]) == 60
    assert item["updatedAt"].endswith("-05:00")

    # Un admin cambió el precio: correrlo de nuevo NO lo pisa ni duplica.
    table.update_item(
        Key={"productId": "p-croissant"},
        UpdateExpression="SET price = :p",
        ExpressionAttributeValues={":p": 5000},
    )
    assert seed_module.main(["--table", TEST_ENV["PRODUCTS_TABLE"], "--file", str(SEED)]) == 0
    assert table.scan()["Count"] == count
    assert int(table.get_item(Key={"productId": "p-croissant"})["Item"]["price"]) == 5000
    assert f"0 insertados, {count} ya existían" in capsys.readouterr().out


def test_dry_run_no_escribe(seed_module, ddb, capsys):
    assert seed_module.main(["--table", TEST_ENV["PRODUCTS_TABLE"], "--file", str(SEED), "--dry-run"]) == 0
    assert ddb.Table(TEST_ENV["PRODUCTS_TABLE"]).scan()["Count"] == 0
    assert "[dry-run]" in capsys.readouterr().out


def test_archivo_invalido_devuelve_2(seed_module, tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("[]")
    assert seed_module.main(["--table", "x", "--file", str(bad)]) == 2
    assert "Error" in capsys.readouterr().err


def test_seed_publica_catalogo(seed_module, ddb, assets_bucket, capsys):
    args = [
        "--table",
        TEST_ENV["PRODUCTS_TABLE"],
        "--file",
        str(SEED),
        "--publish-catalog",
        "--bucket",
        TEST_ENV["ASSETS_BUCKET"],
        "--assets-base-url",
        "https://cdn.example.test/",
    ]
    assert seed_module.main(args) == 0
    catalog = read_catalog(assets_bucket)
    assert len(catalog["body"]["products"]) == len(json.loads(SEED.read_text()))
    assert catalog["CacheControl"] == "max-age=60"
    assert "catalog.json publicado" in capsys.readouterr().out


def test_publish_catalog_exige_bucket(seed_module):
    with pytest.raises(SystemExit):
        seed_module.main(["--table", "x", "--publish-catalog"])
