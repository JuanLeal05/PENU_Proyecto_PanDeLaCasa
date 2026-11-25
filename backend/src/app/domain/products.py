"""Productos: slug, validación de escrituras del admin y vista ``Product`` (contratos 02 y 03 §1)."""

import re
import unicodedata
from collections.abc import Mapping
from typing import Any

from app.http import validation_error

IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
PRODUCT_ID_RE = re.compile(r"^p-[a-z0-9]+(-[a-z0-9]+)*$")
MAX_PRICE = 1_000_000
MAX_DAILY = 10_000
MAX_INVENTORY_ITEMS = 100

# campo → (validador, mensaje). Los textos se recortan antes de validar.
_TEXT_LIMITS = {"name": (2, 80), "description": (0, 300), "category": (2, 40)}


def slugify(text: str, max_length: int = 40) -> str:
    """``"Pan de Queso Ñapa"`` → ``"pan-de-queso-napa"`` (sin tildes, minúsculas, guiones)."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or "producto"


def product_id_for(name: str) -> str:
    return f"p-{slugify(name)}"


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_field(name: str, value: Any, fields: list[str]) -> Any:
    """Valida un campo editable y devuelve el valor normalizado (o ``None`` si es inválido)."""
    if name in _TEXT_LIMITS:
        low, high = _TEXT_LIMITS[name]
        text = value.strip() if isinstance(value, str) else None
        if text is None or not low <= len(text) <= high:
            fields.append(name)
            return None
        return text
    if name == "price":
        if not _is_int(value) or not 1 <= value <= MAX_PRICE:
            fields.append(name)
            return None
        return value
    if name in ("dailyProduction", "stock"):
        if not _is_int(value) or not 0 <= value <= MAX_DAILY:
            fields.append(name)
            return None
        return value
    if name == "active":
        if not isinstance(value, bool):
            fields.append(name)
            return None
        return value
    fields.append(name)
    return None


def validate_product_create(body: Mapping[str, Any]) -> dict[str, Any]:
    """``POST /api/admin/products``: name, category, price y dailyProduction son obligatorios."""
    fields: list[str] = []
    data = {
        "name": body.get("name"),
        "description": body.get("description", ""),
        "category": body.get("category"),
        "price": body.get("price"),
        "dailyProduction": body.get("dailyProduction"),
        "active": body.get("active", True),
    }
    clean = {name: _check_field(name, value, fields) for name, value in data.items()}
    unknown = sorted(set(body) - set(data))
    fields.extend(unknown)
    if fields:
        raise validation_error("Revisa los datos del producto.", fields)
    return clean


def validate_product_update(body: Mapping[str, Any], product_id: str, images_prefix: str) -> dict[str, Any]:
    """``PUT /api/admin/products/{id}``: actualización parcial; ``imageKey`` debe ser de ESTE producto."""
    editable = {"name", "description", "category", "price", "dailyProduction", "active"}
    fields: list[str] = []
    clean: dict[str, Any] = {}
    for name, value in body.items():
        if name == "imageKey":
            prefix = f"{images_prefix}{product_id}/"
            ok = (
                isinstance(value, str)
                and value.startswith(prefix)
                and ".." not in value
                and re.fullmatch(r"[a-z0-9]{1,32}\.(jpg|png|webp)", value[len(prefix) :]) is not None
            )
            if ok:
                clean[name] = value
            else:
                fields.append(name)
        elif name in editable:
            clean[name] = _check_field(name, value, fields)
        else:
            fields.append(name)
    if not body:
        fields.append("body")
    if fields:
        raise validation_error("Revisa los datos del producto.", fields)
    return clean


def validate_image_request(body: Mapping[str, Any]) -> tuple[str, str]:
    """Devuelve ``(contentType, extensión)``; solo JPEG, PNG y WebP."""
    content_type = body.get("contentType")
    if content_type not in IMAGE_TYPES:
        raise validation_error("La foto debe ser JPEG, PNG o WebP.", ["contentType"])
    return content_type, IMAGE_TYPES[content_type]


def validate_inventory(body: Mapping[str, Any]) -> list[dict[str, Any]]:
    """``PUT /api/admin/inventory``: ``items[]`` con ``productId``, ``stock`` y ``dailyProduction`` (opc.)."""
    items = body.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_INVENTORY_ITEMS:
        raise validation_error("Envía entre 1 y 100 productos.", ["items"])
    fields: list[str] = []
    clean: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(items):
        item = item if isinstance(item, Mapping) else {}
        product_id = item.get("productId")
        if not isinstance(product_id, str) or not PRODUCT_ID_RE.match(product_id):
            fields.append(f"items[{index}].productId")
            continue
        entry: dict[str, Any] = {"productId": product_id}
        local: list[str] = []
        entry["stock"] = _check_field("stock", item.get("stock"), local)
        if "dailyProduction" in item:
            entry["dailyProduction"] = _check_field("dailyProduction", item["dailyProduction"], local)
        fields.extend(f"items[{index}].{name}" for name in local)
        clean[product_id] = entry  # si un producto se repite, gana la última línea
    if fields:
        raise validation_error("Revisa el inventario.", fields)
    return list(clean.values())


def image_url(image_key: str | None, assets_base_url: str) -> str | None:
    if not image_key:
        return None
    return f"{assets_base_url}/{image_key}" if assets_base_url else f"/{image_key}"


def to_product(item: Mapping[str, Any], assets_base_url: str) -> dict[str, Any]:
    """Objeto ``Product`` del contrato 02."""
    return {
        "productId": item["productId"],
        "name": item.get("name", ""),
        "description": item.get("description", ""),
        "category": item.get("category", ""),
        "price": int(item.get("price", 0)),
        "imageUrl": image_url(item.get("imageKey"), assets_base_url),
        "dailyProduction": int(item.get("dailyProduction", 0)),
        "stock": int(item.get("stock", 0)),
        "active": bool(item.get("active", False)),
        "updatedAt": item.get("updatedAt"),
    }


def sort_key(item: Mapping[str, Any]) -> tuple[str, str]:
    return (str(item.get("category", "")).lower(), str(item.get("name", "")).lower())
