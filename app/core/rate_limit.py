"""Rate limit theo cửa sổ cố định 1 phút, lưu ở Redis.

Redis lỗi -> fail-open có cảnh báo (docs/ARCHITECTURE.md §5): không để sự cố Redis làm chatbot ngừng.
Lớp này không phụ thuộc FastAPI để test được bằng Redis giả.
"""
import logging
import time
from collections.abc import Callable

from app.core.errors import RateLimited

log = logging.getLogger("app.rate_limit")

WINDOW_SECONDS = 60


class RateLimiter:
    def __init__(self, redis, limit_per_minute: int, *, clock: Callable[[], float] = time.time):
        self.redis = redis
        self.limit = limit_per_minute
        self._clock = clock

    @property
    def enabled(self) -> bool:
        return self.redis is not None and self.limit > 0

    async def check(self, identity: str) -> None:
        """Raise RateLimited (429 + Retry-After) nếu `identity` vượt hạn mức trong phút hiện tại."""
        if not self.enabled:
            return
        now = int(self._clock())
        bucket = now // WINDOW_SECONDS
        key = f"rl:{identity}:{bucket}"
        try:
            pipe = self.redis.pipeline(transaction=True)
            pipe.incr(key)
            pipe.expire(key, WINDOW_SECONDS * 2)       # TTL luôn đặt cùng INCR: không bao giờ để key vĩnh viễn
            count, _ = await pipe.execute()
        except Exception:  # noqa: BLE001 - fail-open
            log.warning("Rate limit bỏ qua do Redis lỗi", exc_info=True)
            return
        if int(count) > self.limit:
            retry_after = WINDOW_SECONDS - (now % WINDOW_SECONDS)
            raise RateLimited(
                "Bạn gửi quá nhiều yêu cầu. Vui lòng thử lại sau ít phút.",
                headers={"Retry-After": str(retry_after)},
            )
