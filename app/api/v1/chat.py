from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user
from app.schemas.chat_schema import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse, response_model_by_alias=True)
async def chat(body: ChatRequest, user: CurrentUser = Depends(get_current_user)) -> ChatResponse:
    """Router chỉ nhận request và gọi ChatService (không gọi RAG/LLM trực tiếp).

    TODO(Member 01): validate độ dài theo settings.message_max_length, rate limit,
    gọi `ChatService.handle(user, body)`.
    """
    raise NotImplementedError


@router.post("/chat/stream")
async def chat_stream(body: ChatRequest, user: CurrentUser = Depends(get_current_user)):
    """SSE: các event `token`, `sources`, `done`, `error` (xem docs/CONTRACTS.md)."""
    raise NotImplementedError
