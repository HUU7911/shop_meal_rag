from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Conversation


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

    async def soft_delete(self, conversation_id: str) -> bool:
        stmt = (
            update(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.deleted_at.is_(None),
            )
            .values(deleted_at=func.now())
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0
