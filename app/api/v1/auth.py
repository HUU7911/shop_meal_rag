from fastapi import APIRouter, Depends, Header, Request, Response, status

from app.core.dependencies import AuthServiceDep, CurrentUserDep, enforce_auth_rate_limit
from app.core.security import client_ip, require_login
from app.schemas.auth_schema import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    UserOut,
)

router = APIRouter()
_LIMIT = [Depends(enforce_auth_rate_limit)]


def _origin(request: Request, user_agent: str | None) -> dict:
    return {"ip": client_ip(request), "user_agent": user_agent}


@router.post("/register", response_model=AuthResponse, response_model_by_alias=True,
             status_code=status.HTTP_201_CREATED, dependencies=_LIMIT)
async def register(body: RegisterRequest, request: Request, service: AuthServiceDep,
                   user_agent: str | None = Header(default=None)) -> AuthResponse:
    """Đăng ký tài khoản (vai trò USER) và đăng nhập luôn."""
    return await service.register(body.email, body.password, body.full_name, **_origin(request, user_agent))


@router.post("/login", response_model=AuthResponse, response_model_by_alias=True, dependencies=_LIMIT)
async def login(body: LoginRequest, request: Request, service: AuthServiceDep,
                user_agent: str | None = Header(default=None)) -> AuthResponse:
    """Đăng nhập bằng email và mật khẩu. Trả access token (ngắn hạn) và refresh token (dài hạn, xoay vòng)."""
    return await service.login(body.email, body.password, **_origin(request, user_agent))


@router.post("/refresh", response_model=AuthResponse, response_model_by_alias=True, dependencies=_LIMIT)
async def refresh(body: RefreshRequest, request: Request, service: AuthServiceDep,
                  user_agent: str | None = Header(default=None)) -> AuthResponse:
    """Đổi refresh token lấy cặp token mới. Refresh token cũ bị thu hồi ngay."""
    return await service.refresh(body.refresh_token, **_origin(request, user_agent))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, service: AuthServiceDep) -> Response:
    """Đăng xuất thiết bị hiện tại (thu hồi refresh token). Access token còn dùng được tới khi hết hạn."""
    await service.logout(body.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: CurrentUserDep, service: AuthServiceDep) -> Response:
    """Đăng xuất mọi thiết bị."""
    require_login(user)
    await service.logout_all(user.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut, response_model_by_alias=True)
async def me(user: CurrentUserDep, service: AuthServiceDep) -> UserOut:
    require_login(user)
    return await service.me(user.user_id)


@router.put("/password", response_model=AuthResponse, response_model_by_alias=True, dependencies=_LIMIT)
async def change_password(body: ChangePasswordRequest, request: Request, user: CurrentUserDep,
                          service: AuthServiceDep, user_agent: str | None = Header(default=None)) -> AuthResponse:
    """Đổi mật khẩu: mọi phiên cũ bị thu hồi, trả cặp token mới cho thiết bị đang dùng."""
    require_login(user)
    return await service.change_password(user.user_id, body.current_password, body.new_password,
                                         **_origin(request, user_agent))