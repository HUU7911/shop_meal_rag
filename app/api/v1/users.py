from typing import Annotated

from fastapi import APIRouter, Query

from app.core.dependencies import AdminDep, AuthServiceDep
from app.schemas.auth_schema import RolesUpdate, StatusUpdate, UserOut
from app.schemas.common_schema import Page

router = APIRouter()


@router.get("", response_model=Page[UserOut], response_model_by_alias=True)
async def list_users(
    _admin: AdminDep,
    service: AuthServiceDep,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="pageSize")] = 20,
) -> Page[UserOut]:
    """Danh sách người dùng (chỉ ADMIN)."""
    return await service.list_users(page, page_size)


@router.patch("/{user_id}/roles", response_model=UserOut, response_model_by_alias=True)
async def set_roles(user_id: str, body: RolesUpdate, _admin: AdminDep, service: AuthServiceDep) -> UserOut:
    """Cấp hoặc gỡ vai trò ADMIN (chỉ ADMIN). Không gỡ được quản trị viên cuối cùng.
    Token đang dùng giữ vai trò cũ tới khi hết hạn; lần làm mới token kế tiếp sẽ nhận vai trò mới."""
    return await service.set_roles(user_id, list(body.roles))


@router.patch("/{user_id}/status", response_model=UserOut, response_model_by_alias=True)
async def set_status(user_id: str, body: StatusUpdate, admin: AdminDep, service: AuthServiceDep) -> UserOut:
    """Khóa/mở khóa tài khoản (chỉ ADMIN). Khóa sẽ thu hồi toàn bộ refresh token của người đó."""
    return await service.set_active(admin.user_id, user_id, body.active)