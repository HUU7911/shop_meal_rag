"""Dựng các service một lần trong lifespan (main.py) và gắn vào app.state.services."""
from dataclasses import dataclass

from app.core.rate_limit import RateLimiter
from app.db.unit_of_work import make_uow_factory
from app.services.chat_service import ChatService
from app.services.conversation_service import ConversationService
from app.services.feedback_service import FeedbackService
from app.services.health_service import HealthService
from app.services.history_service import HistoryService
from app.services.ingestion_service import IngestionService


@dataclass
class Services:
    chat: ChatService
    conversations: ConversationService
    history: HistoryService
    feedback: FeedbackService
    health: HealthService
    ingestion: IngestionService
    rate_limiter: RateLimiter


def build_services(settings, *, db_engine, session_factory, redis, rag_engine) -> Services:
    uow_factory = make_uow_factory(session_factory)
    conversations = ConversationService(uow_factory)
    history = HistoryService(
        uow_factory, redis,
        max_turns=settings.history_max_turns, max_tokens=settings.history_max_tokens,
    )
    return Services(
        chat=ChatService(conversations=conversations, history=history, rag_engine=rag_engine),
        conversations=conversations,
        history=history,
        feedback=FeedbackService(uow_factory),
        health=HealthService(settings, db_engine=db_engine, redis=redis),
        ingestion=IngestionService(uow_factory),
        rate_limiter=RateLimiter(redis, settings.rate_limit_per_minute),
    )
