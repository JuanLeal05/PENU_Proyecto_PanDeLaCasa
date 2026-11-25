"""Logs JSON, enmascarado de datos personales y métricas EMF (contrato 04 §7).

Todo se imprime por stdout: CloudWatch Logs lo recoge y extrae las métricas EMF automáticamente.
"""

import json
import sys
import time
import traceback
from typing import Any

from app.config import load_settings

_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
METRICS_NAMESPACE = "PanDeLaCasa"


def mask_phone(phone: str | None) -> str:
    """``3001234567`` → ``300****567`` (Ley 1581: nunca el número completo en logs)."""
    if not phone:
        return ""
    if len(phone) <= 6:
        return "*" * len(phone)
    return f"{phone[:3]}{'*' * (len(phone) - 6)}{phone[-3:]}"


def mask_email(email: str | None) -> str:
    """``ana@x.com`` → ``a***@x.com``."""
    if not email:
        return ""
    local, sep, domain = email.partition("@")
    if not sep:
        return "***"
    return f"{local[:1]}***@{domain}"


class Logger:
    """Logger que imprime una línea JSON por evento con los campos base del contrato."""

    def __init__(self, function: str, request_id: str = "-") -> None:
        settings = load_settings()
        self.function = function
        self.request_id = request_id
        self.env = settings.env
        self.min_level = _LEVELS.get(settings.log_level, 20)

    def _emit(self, level: str, message: str, fields: dict[str, Any]) -> None:
        if _LEVELS[level] < self.min_level:
            return
        record = {
            "level": level,
            "message": message,
            "env": self.env,
            "function": self.function,
            "requestId": self.request_id,
            **fields,
        }
        print(json.dumps(record, ensure_ascii=False, default=str), file=sys.stdout, flush=True)

    def debug(self, message: str, **fields: Any) -> None:
        self._emit("DEBUG", message, fields)

    def info(self, message: str, **fields: Any) -> None:
        self._emit("INFO", message, fields)

    def warning(self, message: str, **fields: Any) -> None:
        self._emit("WARNING", message, fields)

    def error(self, message: str, exc: BaseException | None = None, **fields: Any) -> None:
        if exc is not None:
            fields["errorType"] = type(exc).__name__
            fields["stackTrace"] = "".join(traceback.format_exception(exc))
        self._emit("ERROR", message, fields)


def get_logger(function: str, context: Any = None) -> Logger:
    """Crea el logger de una invocación tomando ``aws_request_id`` del contexto de Lambda."""
    request_id = getattr(context, "aws_request_id", None) or "-"
    return Logger(function, request_id)


def emit_metric(name: str, value: float = 1, unit: str = "Count", **dimensions: str) -> None:
    """Imprime una métrica en Embedded Metric Format. ``Env`` se agrega siempre como dimensión."""
    dims = {"Env": load_settings().env, **dimensions}
    record = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": METRICS_NAMESPACE,
                    "Dimensions": [list(dims.keys())],
                    "Metrics": [{"Name": name, "Unit": unit}],
                }
            ],
        },
        **dims,
        name: value,
    }
    print(json.dumps(record, separators=(",", ":")), file=sys.stdout, flush=True)
