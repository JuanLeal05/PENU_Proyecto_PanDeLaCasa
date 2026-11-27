"""Carga el catálogo inicial en la tabla de productos (contrato 04 §10).

LO EJECUTA JUAN PABLO (dueño de la cuenta AWS) con sus credenciales, una vez por ambiente:

    cd backend
    python scripts/seed_products.py --table pdc-dev-products --region us-east-1 --dry-run   # revisar
    python scripts/seed_products.py --table pdc-dev-products --region us-east-1

    # Opcional: generar de una vez assets/catalog/catalog.json (si no, lo genera el primer guardado
    # de un producto desde el panel admin). Bucket y URL salen de los outputs de Terraform.
    python scripts/seed_products.py --table pdc-dev-products --publish-catalog \
        --bucket <assets_bucket> --assets-base-url https://<cloudfront_domain>

- Es idempotente: usa ``ConditionExpression="attribute_not_exists(productId)"``, así que se puede
  correr varias veces sin duplicar ni pisar productos editados desde el panel admin.
- Fija ``stock = dailyProduction`` y ``updatedAt`` con la hora de Bogotá.
- Solo usa la biblioteca estándar + boto3.
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import ClientError

BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")
BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_FILE = BACKEND_DIR / "seed" / "products.json"
PRODUCT_ID_RE = re.compile(r"^p-[a-z0-9]+(-[a-z0-9]+)*$")
REQUIRED = ("productId", "name", "description", "category", "price", "dailyProduction", "active")


def load_products(path: Path) -> list[dict[str, Any]]:
    """Lee y valida el JSON. Lanza ``ValueError`` con todos los problemas encontrados."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise ValueError("El archivo debe ser una lista no vacía de productos.")
    problems: list[str] = []
    seen: set[str] = set()
    for index, product in enumerate(data):
        where = f"producto #{index}"
        missing = [field for field in REQUIRED if field not in product]
        if missing:
            problems.append(f"{where}: faltan {', '.join(missing)}")
            continue
        pid = product["productId"]
        if not isinstance(pid, str) or not PRODUCT_ID_RE.match(pid):
            problems.append(f"{where}: productId inválido ({pid!r}); formato p-<slug>")
        if pid in seen:
            problems.append(f"{where}: productId repetido ({pid})")
        seen.add(pid)
        for field in ("price", "dailyProduction"):
            value = product[field]
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or value < (1 if field == "price" else 0)
            ):
                problems.append(f"{where}: {field} debe ser un entero (COP sin decimales)")
        if not isinstance(product["active"], bool):
            problems.append(f"{where}: active debe ser true/false")
    if problems:
        raise ValueError("\n".join(problems))
    return data


def to_item(product: dict[str, Any], now: datetime) -> dict[str, Any]:
    item = {field: product[field] for field in REQUIRED}
    item["stock"] = product["dailyProduction"]
    item["updatedAt"] = now.isoformat(timespec="seconds")
    if product.get("imageKey"):
        item["imageKey"] = product["imageKey"]
    return item


def seed(table: Any, products: list[dict[str, Any]], now: datetime, dry_run: bool = False) -> dict[str, int]:
    """Inserta los productos que no existan. Devuelve el conteo de insertados y omitidos."""
    result = {"inserted": 0, "skipped": 0}
    for product in products:
        item = to_item(product, now)
        if dry_run:
            print(f"[dry-run] insertaría {item['productId']} ({item['name']}) stock={item['stock']}")
            result["inserted"] += 1
            continue
        try:
            table.put_item(Item=item, ConditionExpression="attribute_not_exists(productId)")
        except ClientError as err:
            if err.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            print(f"omitido   {item['productId']} (ya existe)")
            result["skipped"] += 1
        else:
            print(f"insertado {item['productId']}")
            result["inserted"] += 1
    return result


def publish_catalog(table_name: str, bucket: str, assets_base_url: str, region: str) -> int:
    """Reutiliza ``app.catalog.publish_catalog`` (el mismo código que usa la Lambda admin-products)."""
    os.environ.update(
        {
            "PRODUCTS_TABLE": table_name,
            "ASSETS_BUCKET": bucket,
            "ASSETS_BASE_URL": assets_base_url,
            "AWS_DEFAULT_REGION": region,
        }
    )
    src = str(BACKEND_DIR / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from app.catalog import publish_catalog as publish

    catalog = publish()
    return len(catalog["products"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga los productos semilla en DynamoDB.")
    parser.add_argument("--table", required=True, help="p. ej. pdc-dev-products")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--file", type=Path, default=DEFAULT_FILE)
    parser.add_argument("--dry-run", action="store_true", help="solo muestra lo que haría")
    parser.add_argument("--publish-catalog", action="store_true", help="genera catalog.json en S3")
    parser.add_argument("--bucket", help="bucket de assets (output assets_bucket)")
    parser.add_argument("--assets-base-url", help="https://<cloudfront_domain> (sin /assets)")
    args = parser.parse_args(argv)
    if args.publish_catalog and not (args.bucket and args.assets_base_url):
        parser.error("--publish-catalog requiere --bucket y --assets-base-url")

    try:
        products = load_products(args.file)
    except (OSError, ValueError) as err:
        print(f"Error en {args.file}:\n{err}", file=sys.stderr)
        return 2

    table = None if args.dry_run else boto3.resource("dynamodb", region_name=args.region).Table(args.table)
    result = seed(table, products, datetime.now(BOGOTA), dry_run=args.dry_run)
    print(f"Listo en {args.table}: {result['inserted']} insertados, {result['skipped']} ya existían.")
    if args.publish_catalog and not args.dry_run:
        count = publish_catalog(args.table, args.bucket, args.assets_base_url.rstrip("/"), args.region)
        print(f"catalog.json publicado en s3://{args.bucket} con {count} productos activos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
