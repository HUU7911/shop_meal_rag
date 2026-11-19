"""Repository: chỉ truy cập DB (không chứa nghiệp vụ)."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import ChatMessage


class MessageRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add_many(self, messages: list[ChatMessage]) -> None:
        self.session.add_all(messages)
        await self.session.flush()

    async def get_by_id(self, message_id: str) -> ChatMessage | None:
        return await self.session.get(ChatMessage, message_id)

    async def list_recent(self, conversation_id: str, limit: int) -> list[ChatMessage]:
        """`limit` message mới nhất, trả theo thứ tự thời gian TĂNG dần."""
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(reversed(rows))

    async def list_page(
        self, conversation_id: str, offset: int, limit: int
    ) -> tuple[list[ChatMessage], int]:
        """Phân trang theo thứ tự thời gian tăng dần (cũ -> mới)."""
        total = await self.session.scalar(
            select(func.count())
            .select_from(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
        )
        stmt = (
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conversation_id)
            .order_by(ChatMessage.created_at.asc(), ChatMessage.id.asc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows), total or 0
