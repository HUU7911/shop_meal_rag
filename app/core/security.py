"""Xác thực: trích user hiện tại từ JWT (hoặc header đã được Gateway xác minh)."""
from dataclasses import dataclass, field

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError


@dataclass(frozen=True)
class CurrentUser:
    user_id: str | None
    roles: tuple[str, ...] = field(default_factory=tuple)
    token: str | None = None          # giữ lại để gọi Order Service thay mặt user

    @property
    def is_guest(self) -> bool:
        return self.user_id is None

    @property
    def is_admin(self) -> bool:
        return "ADMIN" in self.roles


def decode_jwt(token: str) -> dict:
    """TODO(Member 01): verify chữ ký (JWT_PUBLIC_KEY hoặc JWKS), exp, aud bằng PyJWT."""
    raise NotImplementedError


async def get_current_user(request: Request) -> CurrentUser:
    settings = get_settings()
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:]
        claims = decode_jwt(token)
        return CurrentUser(user_id=str(claims["sub"]), roles=tuple(claims.get("roles", [])), token=token)
    # Chỉ tin header của Gateway khi được bật rõ ràng (chatbot không public trực tiếp).
    if settings.trust_gateway_user_header and (uid := request.headers.get("X-User-Id")):
        return CurrentUser(user_id=uid)
    if settings.allow_guest:
        return CurrentUser(user_id=None)
    raise AuthenticationError("Yêu cầu đăng nhập.")


def require_login(user: CurrentUser) -> CurrentUser:
    if user.is_guest:
        raise AuthenticationError("Vui lòng đăng nhập để sử dụng chức năng này.")
    return user
