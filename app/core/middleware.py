"""Middleware: request ID và thời gian xử lý."""
import logging
import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import request_id_ctx

log = logging.getLogger("app.http")

REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming_id = request.headers.get("X-Request-ID", "")

        if REQUEST_ID_PATTERN.fullmatch(incoming_id):
            request_id = incoming_id
        else:
            request_id = uuid.uuid4().hex

        request.state.request_id = request_id
        context_token = request_id_ctx.set(request_id)
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

            log.info(
                "%s %s completed in %.2fms",
                request.method,
                request.url.path,
                elapsed_ms,
            )

            request_id_ctx.reset(context_token)
