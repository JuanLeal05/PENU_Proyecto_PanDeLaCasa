import json

from app.observability import Logger, emit_metric, get_logger, mask_email, mask_phone
from conftest import read_logs


def test_mask_phone():
    assert mask_phone("3001234567") == "300****567"
    assert mask_phone("") == ""
    assert mask_phone("12345") == "*****"


def test_mask_email():
    assert mask_email("ana@x.com") == "a***@x.com"
    assert mask_email(None) == ""
    assert mask_email("sin-arroba") == "***"


def test_log_json_con_campos_base(capsys, lambda_context):
    log = get_logger("create-order", lambda_context)
    log.info("order_created", orderId="o-1", units=3)
    [record] = read_logs(capsys.readouterr().out)
    assert record == {
        "level": "INFO",
        "message": "order_created",
        "env": "test",
        "function": "create-order",
        "requestId": "req-test-0001",
        "orderId": "o-1",
        "units": 3,
    }


def test_log_respeta_nivel(capsys, monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    log = Logger("fn")
    log.debug("x")
    log.info("y")
    log.warning("order_rejected", code="SLOT_FULL")
    records = read_logs(capsys.readouterr().out)
    assert [r["message"] for r in records] == ["order_rejected"]
    assert records[0]["code"] == "SLOT_FULL"


def test_log_error_con_stack_trace(capsys):
    try:
        raise ValueError("boom")
    except ValueError as exc:
        Logger("fn").error("unhandled_error", exc=exc)
    [record] = read_logs(capsys.readouterr().out)
    assert record["level"] == "ERROR"
    assert record["errorType"] == "ValueError"
    assert "boom" in record["stackTrace"]


def test_emit_metric_formato_emf(capsys):
    emit_metric("OrdersRejected", Reason="SLOT_FULL")
    record = json.loads(capsys.readouterr().out)
    cw = record["_aws"]["CloudWatchMetrics"][0]
    assert cw["Namespace"] == "PanDeLaCasa"
    assert cw["Dimensions"] == [["Env", "Reason"]]
    assert cw["Metrics"] == [{"Name": "OrdersRejected", "Unit": "Count"}]
    assert record["Env"] == "test"
    assert record["Reason"] == "SLOT_FULL"
    assert record["OrdersRejected"] == 1
    assert isinstance(record["_aws"]["Timestamp"], int)
