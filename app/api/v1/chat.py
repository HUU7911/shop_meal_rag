from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.sse import SSE_HEADERS, encode_sse
from app.core.config import get_settings
from app.core.dependencies import ChatServiceDep, CurrentUserDep, enforce_rate_limit
from app.core.errors import ValidationFailed
from app.schemas.chat_schema import ChatRequest, ChatResponse

router = APIRouter()


def _validate_message_length(body: ChatRequest) -> None:
    limit = get_settings().message_max_length
    if len(body.message) > limit:
        raise ValidationFailed(f"Câu hỏi quá dài (tối đa {limit} ký tự).")


@router.post(
    "/chat",
    response_model=ChatResponse,
    response_model_by_alias=True,
    dependencies=[Depends(enforce_rate_limit)],
)
async def chat(body: ChatRequest, user: CurrentUserDep, service: ChatServiceDep) -> ChatResponse:
    """Nhận request và chuyển cho ChatService xử lý."""
    _validate_message_length(body)
    return await service.handle(user, body)


@router.post("/chat/stream", dependencies=[Depends(enforce_rate_limit)])
async def chat_stream(body: ChatRequest, user: CurrentUserDep, service: ChatServiceDep):
    """SSE events: token {text}, sources {sources}, done {ChatResponse}, error {code,message,requestId}.

    Lỗi trước khi bắt đầu stream (validate, 401/403/404/429) trả HTTP status bình thường;
    lỗi giữa chừng được báo bằng sự kiện `error`.
    """
    _validate_message_length(body)
    events = await service.stream(user, body)
    return StreamingResponse(encode_sse(events), media_type="text/event-stream", headers=SSE_HEADERS)
