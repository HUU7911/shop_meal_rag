from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.security import CurrentUser, get_current_user, require_login

router = APIRouter()

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@router.get("/history/{conversation_id}")
async def get_history(
    conversation_id: str,
    user: CurrentUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
):
    """Lấy lịch sử; service phải kiểm tra conversation thuộc user."""
    require_login(user)
    # TODO(Member 01): HistoryService.get_history(
    #     user_id=user.user_id,
    #     conversation_id=conversation_id,
    #     page=page,
    #     page_size=page_size,
    # )
    raise NotImplementedError


@router.delete(
    "/history/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_history(
    conversation_id: str,
    user: CurrentUserDep,
) -> Response:
    """Soft delete conversation và lịch sử liên quan."""
    require_login(user)
    # TODO(Member 01): HistoryService.delete_history(
    #     user_id=user.user_id,
    #     conversation_id=conversation_id,
    # )
    raise NotImplementedError
