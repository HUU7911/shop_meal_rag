"""Repository: chỉ truy cập DB (không chứa nghiệp vụ)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import Feedback


class FeedbackRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_message_and_user(self, message_id: str, user_id: str | None) -> Feedback | None:
        stmt = select(Feedback).where(Feedback.message_id == message_id)
        stmt = stmt.where(
            Feedback.user_id.is_(None) if user_id is None else Feedback.user_id == user_id
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def add(self, feedback: Feedback) -> Feedback:
        self.session.add(feedback)
        await self.session.flush()
        return feedback
