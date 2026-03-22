"""
Structured logging configuration with correlation IDs and CloudWatch-compatible JSON output.

Usage:
    from prism_inspire.core.log_config import logger
    logger.info("Processing request", extra={"user_id": "123", "action": "login"})
"""

import json
import logging
import logging.handlers
import os
import sys
import time
import uuid
from contextvars import ContextVar

# ── Correlation ID for request tracing ────────────────────────────────
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    return correlation_id_var.get()


def set_correlation_id(cid: str | None = None) -> str:
    cid = cid or uuid.uuid4().hex[:16]
    correlation_id_var.set(cid)
    return cid


# ── Log directory ─────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


# ── Structured JSON formatter ─────────────────────────────────────────
class StructuredJsonFormatter(logging.Formatter):
    """
    Outputs structured JSON log lines compatible with CloudWatch Logs,
    ELK, Loki, and other log aggregation systems.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.") + f"{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add correlation ID if present
        cid = correlation_id_var.get("")
        if cid:
            log_entry["correlation_id"] = cid

        # Add any extra fields passed via extra={}
        for key in ("user_id", "role", "method", "path", "status_code",
                     "duration_ms", "ip", "user_agent", "error_type",
                     "request_id", "action"):
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        # Add exception info
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, default=str)


class StandardFormatter(logging.Formatter):
    """Human-readable format for local development."""

    def format(self, record: logging.LogRecord) -> str:
        cid = correlation_id_var.get("")
        cid_str = f" [{cid}]" if cid else ""
        return (
            f"[{self.formatTime(record)}] [{record.levelname}]{cid_str} "
            f"[{record.name}] {record.getMessage()}"
        )


def _is_production() -> bool:
    return os.getenv("APP_ENV", "development") != "development"


def setup_logger(name: str | None = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        return logger

    logger.setLevel(level)

    use_json = _is_production()
    formatter = StructuredJsonFormatter() if use_json else StandardFormatter(datefmt="%Y-%m-%d %H:%M:%S")

    # Console handler (stdout — picked up by CloudWatch agent / Docker logs)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handlers (rotating, always JSON for machine parsing)
    json_fmt = StructuredJsonFormatter()

    info_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, "info.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    info_handler.setFormatter(json_fmt)
    info_handler.setLevel(logging.INFO)
    logger.addHandler(info_handler)

    error_handler = logging.handlers.RotatingFileHandler(
        os.path.join(LOG_DIR, "error.log"), maxBytes=10 * 1024 * 1024, backupCount=5
    )
    error_handler.setFormatter(json_fmt)
    error_handler.setLevel(logging.ERROR)
    logger.addHandler(error_handler)

    return logger


# Default application logger
logger = setup_logger("Prism")
