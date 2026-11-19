"""Xác thực JWT và trích xuất người dùng hiện tại."""
import hmac
from dataclasses import dataclass, field
from functools import lru_cache

import jwt
from fastapi import Request
from jwt import PyJWKClient
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConfigurationError


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
    settings = get_settings()
    algorithm = settings.jwt_algorithm.upper()

    # Chỉ cho phép thuật toán chữ ký bất đối xứng.
    allowed_algorithms = {
        "RS256", "RS384", "RS512",
        "ES256", "ES384", "ES512",
    }

    if algorithm not in allowed_algorithms:
        raise ConfigurationError("JWT_ALGORITHM không được hỗ trợ.")

    try:
        if settings.jwt_jwks_url:
            signing_key = get_jwks_client(
                settings.jwt_jwks_url
            ).get_signing_key_from_jwt(token).key

        elif settings.jwt_public_key:
            signing_key = settings.jwt_public_key.replace("\\n", "\n")

        else:
            raise ConfigurationError(
                "Cần cấu hình JWT_PUBLIC_KEY hoặc JWT_JWKS_URL."
            )

        options = {
            "require": ["exp", "sub"],
            "verify_aud": bool(settings.jwt_audience),
        }

        claims = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=settings.jwt_audience or None,
            options=options,
        )

        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise AuthenticationError("JWT thiếu subject hợp lệ.")

        roles = claims.get("roles", [])

        if isinstance(roles, str):
            roles = [roles]

        if not isinstance(roles, list):
            raise AuthenticationError("JWT roles không hợp lệ.")

        if not all(isinstance(role, str) for role in roles):
            raise AuthenticationError("JWT roles không hợp lệ.")

        # Spring Security thường prefix "ROLE_" -> chuẩn hóa về ADMIN, USER...
        claims["roles"] = [
            role.upper().removeprefix("ROLE_") for role in roles
        ]
        return claims

    except AuthenticationError:
        raise
    except ConfigurationError:
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


def is_valid_internal_key(provided: str | None) -> bool:
    """So khớp X-Internal-Key theo thời gian không đổi (chống timing attack)."""
    configured = get_settings().internal_api_key.get_secret_value()
    if not configured or not provided:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), configured.encode("utf-8"))


def client_identity(request: Request, user: CurrentUser) -> str:
    """Khóa định danh cho rate limit: user_id nếu đã đăng nhập, ngược lại IP client.

    X-Forwarded-For chỉ được tin khi TRUST_GATEWAY_USER_HEADER=true (chatbot không public ra ngoài
    Gateway) - nếu không, client có thể giả header để né rate limit.
    """
    if user.user_id:
        return f"u:{user.user_id}"
    if get_settings().trust_gateway_user_header:
        forwarded = request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        if forwarded:
            return f"ip:{forwarded[:64]}"
    host = request.client.host if request.client else "unknown"
    return f"ip:{host}"
