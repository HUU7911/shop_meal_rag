"""Xác thực JWT, trích xuất người dùng hiện tại và phân quyền theo vai trò."""
import hmac
from dataclasses import dataclass, field
from functools import lru_cache

import jwt
from fastapi import Depends, Request
from jwt import PyJWKClient
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConfigurationError, PermissionDenied
from app.core.tokens import ACCESS_TOKEN_TYPE, ASYMMETRIC, algorithm_of, static_verification_key


@dataclass(frozen=True)
class CurrentUser:
    user_id: str | None
    roles: tuple[str, ...] = field(default_factory=tuple)
    token: str | None = field(default=None, repr=False)   # không để lộ token trong log/repr

    @property
    def is_guest(self) -> bool:
        return self.user_id is None

    @property
    def is_admin(self) -> bool:
        return "ADMIN" in self.roles


@lru_cache(maxsize=1)
def get_jwks_client(url: str) -> PyJWKClient:
    return PyJWKClient(url)


def decode_jwt(token: str) -> dict:
    """Kiểm tra chữ ký, hạn dùng, iss/aud (nếu cấu hình) và loại token; trả claims đã chuẩn hóa roles."""
    settings = get_settings()
    algorithm = algorithm_of(settings)     # chỉ chấp nhận ĐÚNG thuật toán đã cấu hình

    try:
        if algorithm in ASYMMETRIC and settings.jwt_jwks_url:
            key = get_jwks_client(settings.jwt_jwks_url).get_signing_key_from_jwt(token).key
        else:
            key = static_verification_key(settings)
            if key is None:
                raise ConfigurationError("Cần cấu hình JWT_SECRET, JWT_PUBLIC_KEY hoặc JWT_JWKS_URL.")

        claims = jwt.decode(
            token,
            key,
            algorithms=[algorithm],
            audience=settings.jwt_audience or None,
            issuer=settings.jwt_issuer or None,
            leeway=10,
            options={"require": ["exp", "sub"], "verify_aud": bool(settings.jwt_audience)},
        )

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationError("JWT thiếu subject hợp lệ.")

        # Token do hệ thống ngoài cấp có thể không có `typ`; nếu có thì phải là access token.
        token_type = claims.get("typ")
        if token_type is not None and token_type != ACCESS_TOKEN_TYPE:
            raise AuthenticationError("Loại token không hợp lệ.")

        roles = claims.get("roles", [])
        if isinstance(roles, str):
            roles = [roles]
        if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
            raise AuthenticationError("JWT roles không hợp lệ.")

        # Spring Security thường prefix "ROLE_" -> chuẩn hóa về ADMIN, USER...
        claims["roles"] = [role.upper().removeprefix("ROLE_") for role in roles]
        return claims

    except (AuthenticationError, ConfigurationError):
        raise
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Token không hợp lệ hoặc đã hết hạn.") from exc


async def get_current_user(request: Request) -> CurrentUser:
    settings = get_settings()
    authorization = request.headers.get("Authorization", "").strip()

    if authorization:
        scheme, _, credentials = authorization.partition(" ")

        if scheme.lower() != "bearer" or not credentials.strip():
            raise AuthenticationError("Authorization header không hợp lệ.")

        token = credentials.strip()
        claims = await run_in_threadpool(decode_jwt, token)

        return CurrentUser(
            user_id=claims["sub"],
            roles=tuple(claims["roles"]),
            token=token,
        )

    # Chỉ tin header do Gateway xác minh và ghi đè.
    if settings.trust_gateway_user_header:
        user_id = request.headers.get("X-User-Id", "").strip()

        if user_id:
            return CurrentUser(user_id=user_id)

    if settings.allow_guest:
        return CurrentUser(user_id=None)

    raise AuthenticationError("Yêu cầu đăng nhập.")


def require_login(user: CurrentUser) -> CurrentUser:
    if user.is_guest:
        raise AuthenticationError(
            "Vui lòng đăng nhập để sử dụng chức năng này."
        )

    return user


def require_roles(*required: str):
    """Dependency phân quyền: yêu cầu đăng nhập VÀ có ít nhất một trong các vai trò `required`.

        @router.get("/x", dependencies=[Depends(require_roles("ADMIN"))])
        async def x(admin: Annotated[CurrentUser, Depends(require_roles("ADMIN"))]): ...
    """
    wanted = {role.upper() for role in required}

    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        require_login(user)
        if not wanted.intersection(user.roles):
            raise PermissionDenied("Bạn không có quyền thực hiện thao tác này.")
        return user

    return dependency


def is_valid_internal_key(provided: str | None) -> bool:
    """So khớp X-Internal-Key theo thời gian không đổi (chống timing attack)."""
    configured = get_settings().internal_api_key.get_secret_value()
    if not configured or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), configured.encode("utf-8"))


def client_ip(request: Request) -> str:
    """IP client. X-Forwarded-For chỉ được tin khi TRUST_GATEWAY_USER_HEADER=true (chatbot không public ra
    ngoài Gateway) - nếu không, client có thể giả header để né rate limit."""
    if get_settings().trust_gateway_user_header:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if forwarded:
            return forwarded[:64]
    return request.client.host if request.client else "unknown"


def client_identity(request: Request, user: CurrentUser) -> str:
    """Khóa định danh cho rate limit: user_id nếu đã đăng nhập, ngược lại IP client."""
    if user.user_id:
        return f"u:{user.user_id}"
    return f"ip:{client_ip(request)}"