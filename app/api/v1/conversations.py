from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.security import CurrentUser, get_current_user, require_login
from app.schemas.history_schema import ConversationItem

router = APIRouter()

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@router.post(
    "/conversations",
    response_model=ConversationItem,
    response_model_by_alias=True,
)
async def create_conversation(user: CurrentUserDep) -> ConversationItem:
    """Tạo conversation cho user đã đăng nhập."""
    require_login(user)
    # TODO(Member 01): ConversationService.create(user.user_id).
    raise NotImplementedError


@router.get("/conversations")
async def list_conversations(
    user: CurrentUserDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    """Lấy danh sách conversation của user hiện tại."""
    require_login(user)
    # TODO(Member 01): ConversationService.list(user.user_id, page, page_size).
    raise NotImplementedError
