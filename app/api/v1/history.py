from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.core.dependencies import CurrentUserDep, HistoryServiceDep
from app.core.security import require_login
from app.schemas.history_schema import ConversationHistoryResponse

router = APIRouter()


@router.get(
    "/history/{conversation_id}",
    response_model=ConversationHistoryResponse,
    response_model_by_alias=True,
)
async def get_history(
    conversation_id: str,
    user: CurrentUserDep,
    service: HistoryServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 50,
) -> ConversationHistoryResponse:
    """Lấy lịch sử (cũ -> mới); service kiểm tra conversation thuộc user."""
    require_login(user)
    return await service.get_history(
        user_id=user.user_id, conversation_id=conversation_id, page=page, page_size=page_size
    )


@router.delete("/history/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_history(
    conversation_id: str, user: CurrentUserDep, service: HistoryServiceDep
) -> Response:
    """Soft delete conversation và lịch sử liên quan."""
    require_login(user)
    await service.delete_history(user_id=user.user_id, conversation_id=conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
