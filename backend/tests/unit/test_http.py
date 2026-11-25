import base64
from decimal import Decimal

import pytest

from app.http import (
    ApiError,
    admin_username,
    api_handler,
    dispatch,
    get_header,
    json_response,
    parse_body,
    path_param,
    query_param,
)
from conftest import body_of, read_logs


def test_json_response_serializa_decimal():
    resp = json_response(200, {"price": Decimal("4500"), "ratio": Decimal("0.5")})
    assert resp["statusCode"] == 200
    assert resp["headers"]["Content-Type"].startswith("application/json")
    assert body_of(resp) == {"price": 4500, "ratio": 0.5}
    assert '"price": 4500' in resp["body"]


def test_json_response_sin_cuerpo():
    assert "body" not in json_response(204)


def test_parse_body_normal_y_base64():
    assert parse_body({"body": '{"a": 1}'}) == {"a": 1}
    encoded = base64.b64encode('{"nombre": "Ñame"}'.encode()).decode()
    assert parse_body({"body": encoded, "isBase64Encoded": True}) == {"nombre": "Ñame"}
    assert parse_body({}) == {}


@pytest.mark.parametrize("raw", ["{no-json", "[1, 2]", "42"])
def test_parse_body_invalido(raw):
    with pytest.raises(ApiError) as info:
        parse_body({"body": raw})
    assert (info.value.status, info.value.code) == (400, "VALIDATION_ERROR")
    assert info.value.details == {"fields": ["body"]}


def test_headers_y_parametros():
    event = {
        "headers": {"idempotency-key": "abc"},
        "pathParameters": {"orderId": "o-1"},
        "queryStringParameters": {"code": "K7M2QX"},
    }
    assert get_header(event, "Idempotency-Key") == "abc"
    assert get_header(event, "authorization") is None
    assert path_param(event, "orderId") == "o-1"
    assert query_param(event, "code") == "K7M2QX"
    assert query_param({}, "code") is None
    with pytest.raises(ApiError):
        path_param(event, "productId")


def test_admin_username(make_event):
    assert admin_username(make_event("GET /api/admin/orders", username="maria")) == "maria"
    assert admin_username(make_event("GET /api/admin/orders")) == "admin"


def _demo_handler():
    def ok(event, log):
        return json_response(200, {"ok": True})

    def negocio(event, log):
        raise ApiError(409, "SLOT_FULL", "La franja 10:00 ya no tiene cupos.")

    def falla(event, log):
        raise RuntimeError("boom")

    def no_impl(event, log):
        raise ApiError(501, "NOT_IMPLEMENTED", "pendiente")

    routes = {"GET /ok": ok, "GET /negocio": negocio, "GET /falla": falla, "GET /501": no_impl}

    @api_handler("demo")
    def handler(event, log):
        return dispatch(event, log, routes)

    return handler


def test_api_handler_exito_y_log_de_acceso(make_event, lambda_context, capsys):
    resp = _demo_handler()(make_event("GET /ok"), lambda_context)
    assert resp["statusCode"] == 200
    [access] = read_logs(capsys.readouterr().out)
    assert access["message"] == "request"
    assert access["route"] == "GET /ok"
    assert access["status"] == 200
    assert "durationMs" in access


def test_api_handler_error_de_negocio(make_event, lambda_context, capsys):
    resp = _demo_handler()(make_event("GET /negocio"), lambda_context)
    assert resp["statusCode"] == 409
    assert body_of(resp) == {
        "error": {"code": "SLOT_FULL", "message": "La franja 10:00 ya no tiene cupos.", "details": {}}
    }
    rejected = read_logs(capsys.readouterr().out)[0]
    assert (rejected["level"], rejected["code"]) == ("WARNING", "SLOT_FULL")


def test_api_handler_error_no_controlado(make_event, lambda_context, capsys):
    resp = _demo_handler()(make_event("GET /falla"), lambda_context)
    assert resp["statusCode"] == 500
    assert body_of(resp)["error"]["code"] == "INTERNAL_ERROR"
    assert "boom" not in resp["body"]  # el detalle interno no se filtra al cliente
    error = read_logs(capsys.readouterr().out)[0]
    assert error["level"] == "ERROR"
    assert error["requestId"] == "req-test-0001"
    assert "boom" in error["stackTrace"]


def test_api_handler_5xx_de_negocio_es_error(make_event, lambda_context, capsys):
    resp = _demo_handler()(make_event("GET /501"), lambda_context)
    assert resp["statusCode"] == 501
    assert read_logs(capsys.readouterr().out)[0]["level"] == "ERROR"


def test_ruta_desconocida(make_event, lambda_context):
    resp = _demo_handler()(make_event("GET /nada"), lambda_context)
    assert resp["statusCode"] == 404
    assert body_of(resp)["error"]["code"] == "NOT_FOUND"
