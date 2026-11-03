from fastapi import APIRouter, Depends, Header

from app.core.config import get_settings
from app.core.exceptions import PermissionDenied
from app.core.security import CurrentUser, get_current_user

router = APIRouter()


async def require_admin(user: CurrentUser = Depends(get_current_user),
                        x_internal_key: str | None = Header(default=None)) -> None:
    key = get_settings().internal_api_key.get_secret_value()
    if not (user.is_admin or (key and x_internal_key == key)):
        raise PermissionDenied("Chỉ dành cho quản trị.")


@router.post("/ingestion/run", dependencies=[Depends(require_admin)])
async def run_ingestion(mode: str = "incremental"):
    """Kích hoạt ingestion (`full` | `incremental`). TODO: chạy nền và trả run_id."""
    raise NotImplementedError
