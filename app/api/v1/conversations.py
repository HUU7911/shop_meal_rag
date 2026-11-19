from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.dependencies import ConversationServiceDep, CurrentUserDep
from app.core.security import require_login
from app.schemas.common_schema import Page
from app.schemas.history_schema import ConversationItem

router = APIRouter()


@router.post(
    "/conversations",
    response_model=ConversationItem,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    user: CurrentUserDep, service: ConversationServiceDep
) -> ConversationItem:
    """Tạo conversation cho user đã đăng nhập."""
    require_login(user)
    return await service.create(user.user_id)


@router.get(
    "/conversations",
    response_model=Page[ConversationItem],
    response_model_by_alias=True,
)
async def list_conversations(
    user: CurrentUserDep,
    service: ConversationServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> Page[ConversationItem]:
    """Lấy danh sách conversation của user hiện tại (mới hoạt động nhất trước)."""
    require_login(user)
    return await service.list(user.user_id, page, page_size)
