"""Middleware ASGI thuần: X-Request-ID + đo thời gian.

Viết bằng ASGI thuần (không dùng BaseHTTPMiddleware) để SSE streaming không bị buffer,
contextvar request_id còn hiệu lực trong suốt thời gian stream, và thời gian đo là
thời gian của TOÀN BỘ response (kể cả stream), không chỉ tới lúc có header.
"""
import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import request_id_ctx

log = logging.getLogger("app.http")

REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = ""
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex

        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        status_holder = {"status": 0}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            log.info(
                "%s %s -> %s in %.2fms",
                scope.get("method", "-"),
                scope.get("path", "-"),
                status_holder["status"] or "-",
                elapsed_ms,
            )
            request_id_ctx.reset(token)
