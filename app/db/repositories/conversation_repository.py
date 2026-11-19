from datetime import datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import ChatMessage, Conversation, Feedback
from app.db.types import utcnow


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        await self.session.flush()
        await self.session.refresh(conversation)
        return conversation

    async def get_by_id(self, conversation_id: str) -> Conversation | None:
        stmt = select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.deleted_at.is_(None),
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[Conversation], int]:
        conditions = (
            Conversation.user_id == user_id,
            Conversation.deleted_at.is_(None),
        )

        count_stmt = select(func.count()).select_from(Conversation).where(*conditions)
        total = await self.session.scalar(count_stmt)

        stmt = (
            select(Conversation)
            .where(*conditions)
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)

        return list(result.scalars().all()), total or 0

    async def touch(self, conversation_id: str, *, title: str | None = None) -> None:
        """Cập nhật updated_at (danh sách sắp theo hoạt động gần nhất).
        `title` chỉ được ghi nếu conversation chưa có title (lấy từ câu hỏi đầu tiên)."""
        await self.session.execute(
            update(Conversation)
            .where(Conversation.id == conversation_id)
            .values(updated_at=utcnow())
        )
        if title is not None:
            await self.session.execute(
                update(Conversation)
                .where(Conversation.id == conversation_id, Conversation.title.is_(None))
                .values(title=title)
            )

    async def soft_delete(self, conversation_id: str) -> bool:
        stmt = (
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.deleted_at.is_(None),
            )
            .values(deleted_at=utcnow())
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0

    async def purge(self, *, soft_deleted_before: datetime, inactive_before: datetime) -> int:
        """Xóa VĨNH VIỄN (kèm message, feedback) conversation đã soft delete hoặc không hoạt động
        lâu hơn retention. Trả số conversation đã xóa."""
        ids = list(
            (
                await self.session.execute(
                    select(Conversation.id).where(
                        or_(
                            Conversation.deleted_at < soft_deleted_before,
                            Conversation.updated_at < inactive_before,
                        )
                    )
                )
            )
            .scalars()
            .all()
        )
        if not ids:
            return 0
        msg_ids = select(ChatMessage.id).where(ChatMessage.conversation_id.in_(ids))
        await self.session.execute(delete(Feedback).where(Feedback.message_id.in_(msg_ids)))
        await self.session.execute(delete(ChatMessage).where(ChatMessage.conversation_id.in_(ids)))
        await self.session.execute(delete(Conversation).where(Conversation.id.in_(ids)))
        return len(ids)
