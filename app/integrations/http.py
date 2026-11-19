"""HTTP client dùng chung cho Product/Order Service: timeout, retry có giới hạn cho GET, lỗi chuẩn.

Quy tắc (docs/CONTRACTS.md §5):
  * timeout = SERVICE_HTTP_TIMEOUT_SECONDS
  * chỉ retry GET khi lỗi tạm thời (timeout, mất kết nối, 429/502/503/504), tối đa `max_retries`
  * mọi lỗi cuối cùng quy về UpstreamUnavailableError (không lộ chi tiết nội bộ cho người dùng)
  * 404 -> None (không phải lỗi); 401 -> AuthenticationError (token của user hết hạn)
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from app.core.errors import AuthenticationError, UpstreamUnavailableError
from app.core.logging import request_id_ctx

log = logging.getLogger("app.integrations")

RETRYABLE_STATUS = {429, 502, 503, 504}


class ServiceHttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float,
        max_retries: int = 2,
        backoff_seconds: float = 0.2,
        headers: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        name: str = "service",
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.backoff_seconds = backoff_seconds
        self.default_headers = headers or {}
        self._transport = transport
        self._sleep = sleep
        self._name = name
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        # Tạo lười trong event loop đang chạy (client có thể được dựng ngoài loop, vd. CLI ingestion)
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        bearer_token: str | None = None,
    ) -> Any | None:
        """GET -> JSON. Trả None nếu 404 (hoặc 403 khi gọi bằng token user: không tiết lộ tồn tại)."""
        headers = dict(self.default_headers)
        headers["Accept"] = "application/json"
        rid = request_id_ctx.get()
        if rid and rid != "-":
            headers["X-Request-ID"] = rid                 # nối trace xuyên service
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"
        clean_params = {k: v for k, v in (params or {}).items() if v is not None}

        last_reason = "unknown"
        for attempt in range(self.max_retries + 1):
            try:
                resp = await self._get_client().get(path, params=clean_params, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_reason = type(exc).__name__
            else:
                status = resp.status_code
                if status == 404:
                    return None
                if status == 401:
                    raise AuthenticationError("Phiên đăng nhập đã hết hạn, vui lòng đăng nhập lại.")
                if status == 403 and bearer_token:
                    return None
                if status in RETRYABLE_STATUS:
                    last_reason = f"HTTP {status}"
                elif status >= 400:
                    # 4xx còn lại = yêu cầu của ta sai/hợp đồng lệch: không retry, báo lỗi upstream
                    log.warning("%s trả HTTP %s cho %s", self._name, status, path)
                    raise UpstreamUnavailableError(f"{self._name} trả lỗi {status}.")
                else:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        log.warning("%s trả JSON không hợp lệ cho %s", self._name, path)
                        raise UpstreamUnavailableError(f"{self._name} trả dữ liệu không hợp lệ.") from exc

            if attempt < self.max_retries:
                await self._sleep(self.backoff_seconds * (2**attempt))

        log.warning("%s không khả dụng (%s) sau %d lần thử: %s", self._name, last_reason,
                    self.max_retries + 1, path)
        raise UpstreamUnavailableError(f"{self._name} tạm thời không khả dụng.")
