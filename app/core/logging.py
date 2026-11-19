"""Logging chuẩn: có request_id và che dữ liệu nhạy cảm."""
import contextvars
import logging
import re

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)

_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1***"),
    (re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*"), "***jwt***"),
    (re.compile(r"(?i)(x-internal-key[\"':=\s]+)[^\s,;\"']+"), r"\1***"),
    (re.compile(r"\b\d{9,16}\b"), "***"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "***@***"),
]


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()

        for pattern, replacement in _PATTERNS:
            message = pattern.sub(replacement, message)

        record.msg = message
        record.args = ()
        record.request_id = request_id_ctx.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(request_id)s] "
            "%(name)s: %(message)s"
        )
    )
    handler.addFilter(RedactFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
