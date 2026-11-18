from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user
from app.schemas.chat_schema import ChatRequest, ChatResponse

router = APIRouter()

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@router.post("/chat", response_model=ChatResponse, response_model_by_alias=True)
async def chat(body: ChatRequest, user: CurrentUserDep) -> ChatResponse:
    """Nhận request và chuyển cho ChatService xử lý."""
    # TODO(Member 01):
    # 1. Validate message theo settings.message_max_length.
    # 2. Áp dụng rate limit.
    # 3. Gọi ChatService.handle(user, body).
    raise NotImplementedError


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user: CurrentUserDep):
    """SSE events: token, sources, done, error."""
    # TODO(Member 01): gọi ChatService.stream(user, body).
    raise NotImplementedError
