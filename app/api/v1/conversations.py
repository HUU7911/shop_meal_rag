from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user, require_login
from app.schemas.history_schema import ConversationItem

router = APIRouter()


@router.post("/conversations", response_model=ConversationItem, response_model_by_alias=True)
async def create_conversation(user: CurrentUser = Depends(get_current_user)):
    """TODO(Member 01): ConversationService.create(user)."""
    require_login(user)
    raise NotImplementedError


@router.get("/conversations")
async def list_conversations(page: int = 1, page_size: int = 20,
                             user: CurrentUser = Depends(get_current_user)):
    require_login(user)
    raise NotImplementedError
