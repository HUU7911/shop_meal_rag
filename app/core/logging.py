"""Logging chuẩn: có request_id, che dữ liệu nhạy cảm."""
import contextvars
import logging
import re

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

_PATTERNS = [
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]+"), r"\1***"),
    (re.compile(r"\b\d{9,16}\b"), "***"),                          # số điện thoại / thẻ
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "***@***"),          # email
]


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern, repl in _PATTERNS:
            msg = pattern.sub(repl, msg)
        record.msg, record.args = msg, ()
        record.request_id = request_id_ctx.get()
        return True


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s"))
    handler.addFilter(RedactFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
