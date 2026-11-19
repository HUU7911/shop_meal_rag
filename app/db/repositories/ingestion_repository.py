"""Repository cho ingestion_runs (API /admin/ingestion/run). Registry tài liệu thuộc Member 03."""
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.ingestion import IngestionRun
from app.db.types import utcnow


class IngestionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_run(self, mode: str) -> IngestionRun:
        run = IngestionRun(mode=mode, status="RUNNING", started_at=utcnow())
        self.session.add(run)
        await self.session.flush()
        await self.session.refresh(run)
        return run

    async def get_run(self, run_id: int) -> IngestionRun | None:
        return await self.session.get(IngestionRun, run_id)

    async def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        stats: dict[str, int] | None = None,
        error: str | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        stats = stats or {}
        await self.session.execute(
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                status=status,
                finished_at=finished_at or utcnow(),
                added=stats.get("added", 0),
                updated=stats.get("updated", 0),
                deleted=stats.get("deleted", 0),
                skipped=stats.get("skipped", 0),
                error=error,
            )
        )

    async def fail_stale_runs(self, reason: str) -> int:
        """Run còn RUNNING khi app khởi động = tiến trình trước đã chết giữa chừng."""
        result = await self.session.execute(
            update(IngestionRun)
            .where(IngestionRun.status == "RUNNING")
            .values(status="FAILED", finished_at=utcnow(), error=reason)
        )
        return result.rowcount or 0

    async def latest(self, limit: int = 10) -> list[IngestionRun]:
        stmt = select(IngestionRun).order_by(IngestionRun.id.desc()).limit(limit)
        return list((await self.session.execute(stmt)).scalars().all())
