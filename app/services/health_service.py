"""Kiểm tra sức khỏe các phụ thuộc cho /health/ready (ping thật, timeout ngắn, chạy song song).

Phân loại:
  * MySQL            : BẮT BUỘC (lịch sử hội thoại) -> down = "unavailable" (HTTP 503)
  * Qdrant           : BẮT BUỘC khi RAG_ENABLED=true; nếu không thì chỉ cảnh báo
  * Redis, LLM       : tùy chọn (fail-open / có fallback) -> down = "degraded" (HTTP 200)
Không trả chi tiết lỗi nội bộ ra ngoài; chi tiết nằm trong log.
"""
import asyncio
import logging

import httpx
from sqlalchemy import text

log = logging.getLogger("app.services.health")

CHECK_TIMEOUT_SECONDS = 2.0


class HealthService:
    def __init__(self, settings, *, db_engine=None, redis=None):
        self.settings = settings
        self.db_engine = db_engine
        self.redis = redis

    async def _guard(self, name: str, coro) -> str:
        try:
            await asyncio.wait_for(coro, timeout=CHECK_TIMEOUT_SECONDS)
            return "ok"
        except Exception:  # noqa: BLE001 - mọi lỗi (kể cả timeout) = down
            log.warning("Health check '%s' thất bại", name, exc_info=True)
            return "down"

    async def _ping_mysql(self) -> None:
        async with self.db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def _ping_redis(self) -> None:
        await self.redis.ping()

    async def _ping_qdrant(self) -> None:
        headers = {}
        api_key = self.settings.qdrant_api_key.get_secret_value()
        if api_key:
            headers["api-key"] = api_key
        async with httpx.AsyncClient(timeout=CHECK_TIMEOUT_SECONDS) as client:
            resp = await client.get(f"{self.settings.qdrant_url.rstrip('/')}/readyz", headers=headers)
            resp.raise_for_status()

    def _llm_state(self) -> str:
        s = self.settings
        if not s.llm_enabled:
            return "disabled"
        return "configured" if s.llm_model else "misconfigured"

    async def check_all(self) -> dict:
        mysql, redis, qdrant = await asyncio.gather(
            self._guard("mysql", self._ping_mysql()) if self.db_engine is not None else _const("down"),
            self._guard("redis", self._ping_redis()) if self.redis is not None else _const("down"),
            self._guard("qdrant", self._ping_qdrant()),
        )
        checks = {"mysql": mysql, "redis": redis, "qdrant": qdrant, "llm": self._llm_state()}
        return {"status": self.overall_status(checks, rag_enabled=self.settings.rag_enabled), "checks": checks}

    @staticmethod
    def overall_status(checks: dict[str, str], *, rag_enabled: bool) -> str:
        if checks["mysql"] != "ok" or (rag_enabled and checks["qdrant"] != "ok"):
            return "unavailable"
        optional_bad = checks["redis"] != "ok" or checks["qdrant"] != "ok" or checks["llm"] == "misconfigured"
        return "degraded" if optional_bad else "ok"


async def _const(value: str) -> str:
    return value
