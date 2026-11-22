"""Unit of Work: một transaction ngắn, commit khi thoát khối `async with` thành công, rollback khi lỗi.

Service mở UoW cho TỪNG bước (không giữ transaction/connection trong lúc chờ RAG/LLM vài chục giây).
Test thay bằng UoW giả có repository in-memory (xem tests/unit/fakes_db.py).
"""
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.repositories.conversation_repository import ConversationRepository
from app.db.repositories.feedback_repository import FeedbackRepository
from app.db.repositories.ingestion_repository import IngestionRepository
from app.db.repositories.message_repository import MessageRepository
from app.db.repositories.refresh_token_repository import RefreshTokenRepository
from app.db.repositories.user_repository import UserRepository


class UnitOfWork:
    session: AsyncSession
    conversations: ConversationRepository
    messages: MessageRepository
    feedback: FeedbackRepository
    ingestion: IngestionRepository
    users: UserRepository
    refresh_tokens: RefreshTokenRepository

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def __aenter__(self) -> "UnitOfWork":
        self.session = self._session_factory()
        self.conversations = ConversationRepository(self.session)
        self.messages = MessageRepository(self.session)
        self.feedback = FeedbackRepository(self.session)
        self.ingestion = IngestionRepository(self.session)
        self.users = UserRepository(self.session)
        self.refresh_tokens = RefreshTokenRepository(self.session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()


UnitOfWorkFactory = Callable[[], UnitOfWork]


def make_uow_factory(session_factory: async_sessionmaker[AsyncSession]) -> UnitOfWorkFactory:
    return lambda: UnitOfWork(session_factory)