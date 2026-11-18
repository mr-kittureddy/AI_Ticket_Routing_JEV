import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import config

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_RESERVED_RECORD_KEYS = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
        "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
        "relativeCreated", "thread", "threadName", "processName", "process", "message",
        "taskName",
    }
)


def _extra_fields(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _RESERVED_RECORD_KEYS}


class JsonFormatter(logging.Formatter):
    """Emits one JSON object per log line for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_ctx.get(),
            "message": record.getMessage(),
        }
        payload.update(_extra_fields(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for local development."""

    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{datetime.fromtimestamp(record.created).strftime('%H:%M:%S.%f')[:-3]} "
            f"{record.levelname:<7} [{request_id_ctx.get()}] {record.name}: {record.getMessage()}"
        )
        extras = _extra_fields(record)
        if extras:
            base += " | " + " ".join(f"{k}={v}" for k, v in extras.items())
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


_configured = False


def setup_logging() -> None:
    """Configures the root logger once; safe to call multiple times."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    use_console = config.ENVIRONMENT == "development"
    handler.setFormatter(ConsoleFormatter() if use_console else JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if config.DEBUG else logging.INFO)

    for noisy in ("httpx", "httpcore", "chromadb", "urllib3", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Returns a named logger after ensuring logging is configured."""
    setup_logging()
    return logging.getLogger(name)
