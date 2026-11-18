from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header

from app.core.config import get_settings
from app.core.errors import PermissionDenied
from app.core.security import CurrentUser, get_current_user

router = APIRouter()

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]
InternalKey = Annotated[str | None, Header(alias="X-Internal-Key")]


async def require_admin(
    user: CurrentUserDep,
    x_internal_key: InternalKey = None,
) -> None:
    """Cho phép ADMIN hoặc request có internal key hợp lệ."""
    configured_key = get_settings().internal_api_key.get_secret_value()
    is_internal_request = bool(
        configured_key and x_internal_key and x_internal_key == configured_key
    )

    if not (user.is_admin or is_internal_request):
        raise PermissionDenied("Chỉ dành cho quản trị.")


@router.post("/ingestion/run", dependencies=[Depends(require_admin)])
async def run_ingestion(
    mode: Literal["full", "incremental"] = "incremental",
):
    """Kích hoạt ingestion."""
    # TODO(Member 01): gọi IngestionService và trả run_id.
    raise NotImplementedError
