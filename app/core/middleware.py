"""Middleware: X-Request-ID, đo thời gian xử lý. (Rate limit: xem TODO)"""
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import request_id_ctx

log = logging.getLogger("app.http")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = rid
        token = request_id_ctx.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            log.info("%s %s %dms", request.method, request.url.path, elapsed_ms)
            request_id_ctx.reset(token)
        response.headers["X-Request-ID"] = rid
        return response

# TODO(Member 01): RateLimitMiddleware / dependency dùng Redis (sliding window theo user_id/IP).
