"""Cấp và chọn khóa cho JWT; tạo/băm refresh token. Không phụ thuộc FastAPI hay DB.

Hai chế độ (JWT_ALGORITHM):
  * HS256/HS384/HS512: một khóa bí mật dùng chung JWT_SECRET (>= 32 ký tự) để cấp VÀ kiểm token.
    Phù hợp khi chính service này vừa cấp vừa kiểm.
  * RS256/ES256...: JWT_PRIVATE_KEY để cấp; kiểm bằng JWT_PUBLIC_KEY, JWT_JWKS_URL, hoặc suy ra từ khóa riêng.
    Phù hợp khi token do Gateway/Auth service khác cấp (chỉ cần khóa công khai/JWKS).
Danh sách thuật toán khi kiểm luôn chỉ gồm đúng JWT_ALGORITHM đã cấu hình, nên không bị tấn công đổi thuật toán.
"""
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.core.errors import ConfigurationError

SYMMETRIC = {"HS256", "HS384", "HS512"}
ASYMMETRIC = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
MIN_SECRET_BYTES = 32
ACCESS_TOKEN_TYPE = "access"


def algorithm_of(settings) -> str:
    algorithm = settings.jwt_algorithm.upper()
    if algorithm not in SYMMETRIC | ASYMMETRIC:
        raise ConfigurationError("JWT_ALGORITHM không được hỗ trợ.")
    return algorithm


def _pem(value: str) -> str:
    return value.replace("\\n", "\n").strip()


def _secret(settings) -> str:
    secret = settings.jwt_secret.get_secret_value()
    if len(secret.encode("utf-8")) < MIN_SECRET_BYTES:
        raise ConfigurationError("JWT_SECRET cần ít nhất 32 ký tự khi dùng HS256/HS384/HS512.")
    return secret


def has_verification_key(settings) -> bool:
    """Đã đủ cấu hình để KIỂM token chưa (không ném lỗi, dùng khi khởi động)."""
    if algorithm_of(settings) in SYMMETRIC:
        return len(settings.jwt_secret.get_secret_value().encode("utf-8")) >= MIN_SECRET_BYTES
    return bool(settings.jwt_public_key or settings.jwt_jwks_url or settings.jwt_private_key.get_secret_value())


def can_issue(settings) -> bool:
    """Đã đủ cấu hình để CẤP token chưa."""
    if algorithm_of(settings) in SYMMETRIC:
        return len(settings.jwt_secret.get_secret_value().encode("utf-8")) >= MIN_SECRET_BYTES
    return bool(settings.jwt_private_key.get_secret_value())


def signing_key(settings) -> str:
    if algorithm_of(settings) in SYMMETRIC:
        return _secret(settings)
    private = _pem(settings.jwt_private_key.get_secret_value())
    if not private:
        raise ConfigurationError("Cần JWT_PRIVATE_KEY để cấp token (RS256/ES256), hoặc dùng HS256 với JWT_SECRET.")
    return private


def static_verification_key(settings) -> str | None:
    """Khóa kiểm chữ ký không cần JWKS. None nếu chưa cấu hình."""
    if algorithm_of(settings) in SYMMETRIC:
        return _secret(settings)
    if settings.jwt_public_key:
        return _pem(settings.jwt_public_key)
    private = _pem(settings.jwt_private_key.get_secret_value())
    if private:
        from cryptography.hazmat.primitives import serialization

        key = serialization.load_pem_private_key(private.encode("utf-8"), password=None)
        return key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode("ascii")
    return None


def create_access_token(
    settings, *, user_id: str, roles: list[str] | tuple[str, ...], email: str | None = None,
    now: datetime | None = None,
) -> tuple[str, int]:
    """Trả (token, số giây hiệu lực)."""
    now = now or datetime.now(UTC)
    ttl = timedelta(minutes=settings.jwt_access_ttl_minutes)
    claims: dict = {
        "sub": user_id,
        "roles": list(roles),
        "typ": ACCESS_TOKEN_TYPE,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    if settings.jwt_issuer:
        claims["iss"] = settings.jwt_issuer
    if settings.jwt_audience:
        claims["aud"] = settings.jwt_audience
    if email:
        claims["email"] = email
    token = jwt.encode(claims, signing_key(settings), algorithm=algorithm_of(settings))
    return token, int(ttl.total_seconds())


def new_refresh_token() -> str:
    """Chuỗi ngẫu nhiên 384 bit. Chỉ trả cho client MỘT lần; DB chỉ lưu bản băm."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    # SHA-256 là đủ vì token có entropy cao (khác mật khẩu do người dùng đặt)
    return hashlib.sha256(token.encode("utf-8")).hexdigest()