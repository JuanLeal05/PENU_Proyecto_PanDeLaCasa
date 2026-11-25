"""Lambda ``admin-products`` (JWT): productos, foto con URL prefirmada e inventario (contrato 02).

Toda escritura de producto (crear, editar, desactivar) republica ``catalog.json``.
"""

import secrets
import uuid
from typing import Any

from app import aws, clock
from app.catalog import publish_catalog
from app.config import load_settings, require_env
from app.domain import products as domain
from app.http import (
    ApiError,
    Response,
    admin_username,
    api_handler,
    dispatch,
    json_response,
    not_found,
    parse_body,
    path_param,
)
from app.observability import Logger
from app.repositories import products_repo

UPLOAD_EXPIRES_SECONDS = 300
MAX_ID_ATTEMPTS = 5


def _view(item: dict[str, Any]) -> dict[str, Any]:
    return domain.to_product(item, load_settings().assets_base_url)


def _publish(log: Logger) -> None:
    catalog = publish_catalog()
    log.info("catalog_published", products=len(catalog["products"]))


def list_products(event: dict[str, Any], log: Logger) -> Response:
    items = sorted(products_repo.scan_all(), key=domain.sort_key)
    return json_response(200, {"products": [_view(item) for item in items]})


def create_product(event: dict[str, Any], log: Logger) -> Response:
    data = domain.validate_product_create(parse_body(event))
    now = clock.iso(clock.now())
    base_id = domain.product_id_for(data["name"])
    item = {**data, "stock": data["dailyProduction"], "updatedAt": now}
    for attempt in range(MAX_ID_ATTEMPTS):
        # Si el slug ya existe, se agrega un sufijo corto aleatorio.
        item["productId"] = base_id if attempt == 0 else f"{base_id}-{secrets.token_hex(2)}"
        if products_repo.put_if_absent(item):
            break
    else:
        raise RuntimeError(f"No se pudo generar un productId libre para {base_id}")
    log.info("product_created", productId=item["productId"], by=admin_username(event))
    _publish(log)
    return json_response(201, _view(item))


def update_product(event: dict[str, Any], log: Logger) -> Response:
    product_id = path_param(event, "productId")
    changes = domain.validate_product_update(parse_body(event), product_id, load_settings().images_prefix)
    item = products_repo.update_fields(product_id, changes, clock.iso(clock.now()))
    if item is None:
        raise not_found("El producto no existe.")
    log.info("product_updated", productId=product_id, fields=sorted(changes), by=admin_username(event))
    _publish(log)
    return json_response(200, _view(item))


def delete_product(event: dict[str, Any], log: Logger) -> Response:
    """Borrado lógico: ``active = false``. El historial de pedidos sigue intacto."""
    product_id = path_param(event, "productId")
    if products_repo.update_fields(product_id, {"active": False}, clock.iso(clock.now())) is None:
        raise not_found("El producto no existe.")
    log.info("product_deactivated", productId=product_id, by=admin_username(event))
    _publish(log)
    return {"statusCode": 204, "headers": {}}


def image_upload_url(event: dict[str, Any], log: Logger) -> Response:
    """URL prefirmada para que el navegador suba la foto DIRECTO a S3 (la Lambda no toca el archivo)."""
    product_id = path_param(event, "productId")
    content_type, extension = domain.validate_image_request(parse_body(event))
    if products_repo.get(product_id) is None:
        raise not_found("El producto no existe.")
    image_key = f"{load_settings().images_prefix}{product_id}/{uuid.uuid4().hex[:8]}.{extension}"
    upload_url = aws.s3().generate_presigned_url(
        "put_object",
        Params={"Bucket": require_env("ASSETS_BUCKET"), "Key": image_key, "ContentType": content_type},
        ExpiresIn=UPLOAD_EXPIRES_SECONDS,
    )
    log.info("image_upload_url", productId=product_id, imageKey=image_key)
    return json_response(
        200, {"uploadUrl": upload_url, "imageKey": image_key, "expiresIn": UPLOAD_EXPIRES_SECONDS}
    )


def update_inventory(event: dict[str, Any], log: Logger) -> Response:
    """Un ``UpdateItem`` por producto (no transaccional: es un ajuste manual del admin).

    Antes de escribir se verifica que todos existan, para no dejar el inventario a medias.
    Se usa ``GetItem`` (no ``BatchGetItem``) porque es lo que permite la matriz IAM (contrato 03 §6).
    """
    items = domain.validate_inventory(parse_body(event))
    missing = [item["productId"] for item in items if products_repo.get(item["productId"]) is None]
    if missing:
        raise ApiError(404, "NOT_FOUND", "Algún producto no existe.", {"productIds": missing})
    now = clock.iso(clock.now())
    updated = []
    for item in items:
        changes = {key: value for key, value in item.items() if key != "productId"}
        result = products_repo.update_fields(item["productId"], changes, now)
        if result is not None:
            updated.append(result)
    log.info("inventory_updated", products=len(updated), by=admin_username(event))
    return json_response(200, {"products": [_view(item) for item in sorted(updated, key=domain.sort_key)]})


ROUTES = {
    "GET /api/admin/products": list_products,
    "POST /api/admin/products": create_product,
    "PUT /api/admin/products/{productId}": update_product,
    "DELETE /api/admin/products/{productId}": delete_product,
    "POST /api/admin/products/{productId}/image": image_upload_url,
    "PUT /api/admin/inventory": update_inventory,
}


@api_handler("admin-products")
def handler(event: dict[str, Any], log: Logger) -> Response:
    return dispatch(event, log, ROUTES)
