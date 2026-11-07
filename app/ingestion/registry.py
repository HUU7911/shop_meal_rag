"""Đọc/ghi bảng ingestion_documents & ingestion_runs trong MySQL.

Incremental logic:
So sánh content_hash nguồn với registry:
  - ADD    : tài liệu mới chưa có trong registry
  - UPDATE : tài liệu đã có nhưng content_hash bị thay đổi
  - SKIP   : tài liệu có content_hash hoàn toàn trùng khớp
  - DELETE : tài liệu có trong registry nhưng không còn tồn tại ở nguồn hoặc enabled=false
"""
import logging
from datetime import datetime, timezone
from typing import Any

try:
    from sqlalchemy import select, update
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.db.models.ingestion import IngestionDocument, IngestionRun
except ImportError:
    select = update = None
    AsyncSession = Any
    IngestionDocument = IngestionRun = None

log = logging.getLogger("app.ingestion.registry")


class IngestionRegistry:
    def __init__(self, session: AsyncSession | None = None):
        self.session = session

    async def plan(self, content_type: str, source_hashes: dict[str, str]) -> dict[str, list[str]]:
        """Lập kế hoạch đồng bộ (ADD, UPDATE, DELETE, SKIP) cho một loại nội dung."""
        if self.session is None:
            # Khi chưa kết nối DB, coi toàn bộ tài liệu nguồn là ADD
            log.warning("Chưa có DB session, thực hiện chế độ full ADD cho %s", content_type)
            return {
                "add": list(source_hashes.keys()),
                "update": [],
                "delete": [],
                "skip": [],
            }

        stmt = select(IngestionDocument).where(
            IngestionDocument.content_type == content_type,
            IngestionDocument.status == "ACTIVE",
        )
        result = await self.session.execute(stmt)
        existing_docs = {doc.source_id: doc for doc in result.scalars().all()}

        to_add: list[str] = []
        to_update: list[str] = []
        to_skip: list[str] = []

        for source_id, curr_hash in source_hashes.items():
            if source_id not in existing_docs:
                to_add.append(source_id)
            elif existing_docs[source_id].content_hash != curr_hash:
                to_update.append(source_id)
            else:
                to_skip.append(source_id)

        # Tài liệu có trong DB nhưng không còn ở nguồn -> DELETE
        to_delete: list[str] = [sid for sid in existing_docs if sid not in source_hashes]

        plan_summary = {
            "add": to_add,
            "update": to_update,
            "delete": to_delete,
            "skip": to_skip,
        }
        log.info("Plan cho %s: %d add, %d update, %d delete, %d skip",
                 content_type, len(to_add), len(to_update), len(to_delete), len(to_skip))
        return plan_summary

    async def save_document(self, content_type: str, source_id: str, content_hash: str,
                            chunk_count: int, version: str | None = None, kb_version: str = "v1") -> None:
        """Ghi nhận hoặc cập nhật tài liệu trong registry."""
        if self.session is None:
            return

        stmt = select(IngestionDocument).where(
            IngestionDocument.content_type == content_type,
            IngestionDocument.source_id == source_id,
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()

        if doc is None:
            doc = IngestionDocument(
                content_type=content_type,
                source_id=source_id,
                content_hash=content_hash,
                chunk_count=chunk_count,
                version=version,
                status="ACTIVE",
                kb_version=kb_version,
            )
            self.session.add(doc)
        else:
            doc.content_hash = content_hash
            doc.chunk_count = chunk_count
            doc.version = version
            doc.status = "ACTIVE"
            doc.kb_version = kb_version
            doc.updated_at = datetime.now(timezone.utc)

        await self.session.commit()

    async def mark_deleted(self, content_type: str, source_id: str) -> None:
        """Đánh dấu tài liệu đã bị xóa khỏi Knowledge Base."""
        if self.session is None:
            return

        stmt = (
            update(IngestionDocument)
            .where(
                IngestionDocument.content_type == content_type,
                IngestionDocument.source_id == source_id,
            )
            .values(status="DELETED", updated_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)
        await self.session.commit()

    async def start_run(self, mode: str) -> int | None:
        """Bắt đầu một lượt chạy ingestion, trả về run_id."""
        if self.session is None:
            return None

        run = IngestionRun(mode=mode, status="RUNNING")
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return run.id

    async def finish_run(self, run_id: int | None, stats: dict[str, int], error: str | None = None) -> None:
        """Kết thúc lượt chạy và ghi nhận thống kê."""
        if self.session is None or run_id is None:
            return

        stmt = (
            update(IngestionRun)
            .where(IngestionRun.id == run_id)
            .values(
                finished_at=datetime.now(timezone.utc),
                status="FAILED" if error else "COMPLETED",
                added=stats.get("added", 0),
                updated=stats.get("updated", 0),
                deleted=stats.get("deleted", 0),
                skipped=stats.get("skipped", 0),
                error=error,
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()
