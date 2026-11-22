"""Xóa vĩnh viễn lịch sử quá hạn (HISTORY_RETENTION_DAYS): conversation không hoạt động quá hạn,
hoặc đã soft delete quá 7 ngày. Chạy định kỳ bằng cron: `make purge` / `python -m scripts.purge_history`.
"""
import asyncio
import logging
from datetime import timedelta

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import create_engine_and_sessionmaker
from app.db.types import utcnow
from app.db.unit_of_work import make_uow_factory

SOFT_DELETE_GRACE_DAYS = 7
log = logging.getLogger("scripts.purge_history")


async def main() -> int:
    settings = get_settings()
    setup_logging(settings.log_level)
    engine, session_factory = create_engine_and_sessionmaker()
    try:
        now = utcnow()
        async with make_uow_factory(session_factory)() as uow:
            purged = await uow.conversations.purge(
                soft_deleted_before=now - timedelta(days=SOFT_DELETE_GRACE_DAYS),
                inactive_before=now - timedelta(days=settings.history_retention_days),
            )
            expired_tokens = await uow.refresh_tokens.delete_expired(now - timedelta(days=SOFT_DELETE_GRACE_DAYS))
        log.info("Đã xóa vĩnh viễn %d conversation quá hạn và %d refresh token hết hạn", purged, expired_tokens)
        return purged
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
