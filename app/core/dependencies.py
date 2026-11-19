"""DI cho FastAPI. Tài nguyên nặng (DB engine, Redis, RAGEngine, services) được dựng một lần trong lifespan
và đọc lại từ `app.state`. Test có thể thay bằng `app.dependency_overrides`."""
from typing import Annotated

from fastapi import Depends, Request

from app.core.security import CurrentUser, client_identity, get_current_user
from app.services.chat_service import ChatService
from app.services.container import Services
from app.services.conversation_service import ConversationService
from app.services.feedback_service import FeedbackService
from app.services.health_service import HealthService
from app.services.history_service import HistoryService
from app.services.ingestion_service import IngestionService


def get_rag_engine(request: Request):
    return request.app.state.rag_engine


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_chat_service(request: Request) -> ChatService:
    return get_services(request).chat


def get_conversation_service(request: Request) -> ConversationService:
    return get_services(request).conversations


def get_history_service(request: Request) -> HistoryService:
    return get_services(request).history


def get_feedback_service(request: Request) -> FeedbackService:
    return get_services(request).feedback


def get_health_service(request: Request) -> HealthService:
    return get_services(request).health


def get_ingestion_service(request: Request) -> IngestionService:
    return get_services(request).ingestion


async def enforce_rate_limit(
    request: Request, user: Annotated[CurrentUser, Depends(get_current_user)]
) -> None:
    """Rate limit theo user (đã đăng nhập) hoặc IP (khách). Vượt hạn mức -> 429 + Retry-After."""
    await get_services(request).rate_limiter.check(client_identity(request, user))


CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
ConversationServiceDep = Annotated[ConversationService, Depends(get_conversation_service)]
HistoryServiceDep = Annotated[HistoryService, Depends(get_history_service)]
FeedbackServiceDep = Annotated[FeedbackService, Depends(get_feedback_service)]
HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]
IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
