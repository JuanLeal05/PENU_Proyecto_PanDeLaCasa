"""Publica ``assets/catalog/catalog.json`` en S3 (contrato 04 §4, ADR-003).

El catálogo es estático y lo sirve CloudFront: es el tráfico más alto y casi nunca cambia, así que
no pasa por Lambda. Se regenera en cada escritura de producto desde el panel admin.
Incluye solo productos activos y NO incluye stock (el stock sale de ``/api/availability``).
"""

import json
from typing import Any

from app import aws, clock
from app.config import load_settings, require_env
from app.domain.products import image_url, sort_key
from app.repositories import products_repo

CATALOG_CACHE_CONTROL = "max-age=60"


def build_catalog(products: list[dict[str, Any]], assets_base_url: str, generated_at: str) -> dict[str, Any]:
    active = sorted((p for p in products if p.get("active") is True), key=sort_key)
    return {
        "generatedAt": generated_at,
        "currency": "COP",
        "products": [
            {
                "productId": p["productId"],
                "name": p.get("name", ""),
                "description": p.get("description", ""),
                "category": p.get("category", ""),
                "price": int(p.get("price", 0)),
                "imageUrl": image_url(p.get("imageKey"), assets_base_url),
            }
            for p in active
        ],
    }


def publish_catalog() -> dict[str, Any]:
    """Genera y sube el catálogo. Devuelve el JSON publicado."""
    settings = load_settings()
    catalog = build_catalog(products_repo.scan_active(), settings.assets_base_url, clock.iso(clock.now()))
    aws.s3().put_object(
        Bucket=require_env("ASSETS_BUCKET"),
        Key=settings.catalog_key,
        Body=json.dumps(catalog, ensure_ascii=False).encode("utf-8"),
        ContentType="application/json",
        CacheControl=CATALOG_CACHE_CONTROL,
    )
    return catalog
