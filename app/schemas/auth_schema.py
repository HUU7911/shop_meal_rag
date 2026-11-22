import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common_schema import CamelModel

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")

Role = Literal["USER", "ADMIN"]


def normalize_email(value: str) -> str:
    return value.strip().lower()


class RegisterRequest(CamelModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)       # chính sách mật khẩu chi tiết do service kiểm
    full_name: str | None = Field(default=None, max_length=100)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, v: str) -> str:
        v = normalize_email(v)
        if not _EMAIL.match(v):
            raise ValueError("email không hợp lệ")
        return v

    @field_validator("full_name")
    @classmethod
    def _clean_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return " ".join(v.split()) or None


class LoginRequest(CamelModel):
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _norm(cls, v: str) -> str:
        return normalize_email(v)


class RefreshRequest(CamelModel):
    refresh_token: str = Field(min_length=20, max_length=256)


class ChangePasswordRequest(CamelModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class RolesUpdate(CamelModel):
    roles: list[Role] = Field(min_length=1, max_length=2)


class StatusUpdate(CamelModel):
    active: bool


class UserOut(CamelModel):
    user_id: str
    email: str
    full_name: str | None = None
    roles: list[str]
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None = None


class TokenPair(CamelModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int                       # số giây hiệu lực của access token


class AuthResponse(TokenPair):
    user: UserOut