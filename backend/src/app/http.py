"""Utilidades HTTP para el payload 2.0 de API Gateway (contrato 02, formato de error).

Los handlers son delgados: el decorador ``api_handler`` se encarga de los errores, del log de
acceso y de serializar la respuesta.
"""

import base64
import binascii
import functools
import json
import time
from collections.abc import Callable, Mapping
from decimal import Decimal
from typing import Any

from app.observability import Logger, get_logger

Response = dict[str, Any]
RouteFn = Callable[[dict[str, Any], Logger], Response]


class ApiError(Exception):
    """Error de negocio o de validación que se devuelve con el formato del contrato 02."""

    def __init__(self, status: int, code: str, message: str, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = dict(details or {})


def validation_error(message: str, fields: list[str] | None = None) -> ApiError:
    return ApiError(400, "VALIDATION_ERROR", message, {"fields": fields or []})


def not_found(message: str = "Recurso no encontrado.") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def not_implemented(route: str) -> ApiError:
    """Solo existe durante el esqueleto (M0); desaparece cuando todas las rutas estén implementadas."""
    return ApiError(501, "NOT_IMPLEMENTED", f"La ruta {route} todavía no está implementada.")


def _json_default(value: Any) -> Any:
    # DynamoDB devuelve Decimal; todos nuestros números son enteros (precios COP, cantidades).
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"Tipo no serializable: {type(value).__name__}")


def dumps(body: Any) -> str:
    return json.dumps(body, ensure_ascii=False, default=_json_default)


def json_response(status: int, body: Any = None, headers: Mapping[str, str] | None = None) -> Response:
    response: Response = {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8", **(headers or {})},
    }
    if body is not None:
        response["body"] = dumps(body)
    return response


def error_response(err: ApiError) -> Response:
    return json_response(
        err.status, {"error": {"code": err.code, "message": err.message, "details": err.details}}
    )


def parse_body(event: Mapping[str, Any]) -> dict[str, Any]:
    """Cuerpo JSON como dict. Soporta ``isBase64Encoded``. Sin cuerpo → ``{}``."""
    raw = event.get("body")
    if raw in (None, ""):
        return {}
    try:
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8")
        data = json.loads(raw)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise validation_error("El cuerpo no es un JSON válido.", ["body"]) from exc
    if not isinstance(data, dict):
        raise validation_error("El cuerpo debe ser un objeto JSON.", ["body"])
    return data


def get_header(event: Mapping[str, Any], name: str) -> str | None:
    """En el payload 2.0 los headers llegan en minúsculas; igual normalizamos por si acaso."""
    headers = event.get("headers") or {}
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def path_param(event: Mapping[str, Any], name: str) -> str:
    value = (event.get("pathParameters") or {}).get(name)
    if not value:
        raise validation_error(f"Falta el parámetro {name}.", [name])
    return value


def query_param(event: Mapping[str, Any], name: str) -> str | None:
    return (event.get("queryStringParameters") or {}).get(name)


def admin_username(event: Mapping[str, Any]) -> str:
    """Usuario del admin autenticado (claim ``username`` del JWT de Cognito)."""
    claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {}) or {}
    return str(claims.get("username") or claims.get("cognito:username") or "admin")


def dispatch(event: Mapping[str, Any], log: Logger, routes: Mapping[str, RouteFn]) -> Response:
    """Enruta por ``routeKey`` (p. ej. ``"GET /api/orders/{orderId}"``)."""
    route_key = event.get("routeKey", "")
    route = routes.get(route_key)
    if route is None:
        raise not_found(f"Ruta no soportada: {route_key or '(vacía)'}")
    return route(dict(event), log)


def api_handler(function: str) -> Callable[[RouteFn], Callable[[dict[str, Any], Any], Response]]:
    """Decorador de handlers HTTP.

    1. ``ApiError`` → su respuesta (4xx de negocio con WARNING; 5xx con ERROR).
    2. Cualquier otra excepción → ERROR con stack trace y ``500 INTERNAL_ERROR``.
    3. Siempre registra la línea de acceso: ruta, estado y duración en ms.
    """

    def decorator(fn: RouteFn) -> Callable[[dict[str, Any], Any], Response]:
        @functools.wraps(fn)
        def wrapper(event: dict[str, Any], context: Any) -> Response:
            log = get_logger(function, context)
            started = time.perf_counter()
            route_key = event.get("routeKey", "")
            try:
                response = fn(event, log)
            except ApiError as err:
                if err.status >= 500:
                    log.error("request_failed", code=err.code, route=route_key)
                else:
                    log.warning("request_rejected", code=err.code, route=route_key, status=err.status)
                response = error_response(err)
            except Exception as exc:  # frontera de la Lambda: nada se escapa sin registrar
                log.error("unhandled_error", exc=exc, route=route_key)
                response = error_response(
                    ApiError(500, "INTERNAL_ERROR", "Ocurrió un error inesperado. Intenta de nuevo.")
                )
            log.info(
                "request",
                route=route_key,
                status=response["statusCode"],
                durationMs=round((time.perf_counter() - started) * 1000, 1),
            )
            return response

        return wrapper

    return decorator
