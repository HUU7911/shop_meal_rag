from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user, require_login

router = APIRouter()


@router.get("/history/{conversation_id}")
async def get_history(conversation_id: str, page: int = 1, page_size: int = 50,
                      user: CurrentUser = Depends(get_current_user)):
    """Phải kiểm tra conversation thuộc về user."""
    require_login(user)
    raise NotImplementedError


@router.delete("/history/{conversation_id}", status_code=204)
async def delete_history(conversation_id: str, user: CurrentUser = Depends(get_current_user)):
    """Soft delete."""
    require_login(user)
    raise NotImplementedError
