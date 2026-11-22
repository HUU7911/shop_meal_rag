"""Đăng ký, đăng nhập, làm mới/thu hồi token, đổi mật khẩu và quản trị người dùng.

Nguyên tắc:
* Mật khẩu chỉ lưu dạng băm scrypt; thông báo lỗi đăng nhập luôn chung chung và email lạ vẫn tốn một lần băm
  để không lộ email nào đã đăng ký.
* Sai mật khẩu quá AUTH_MAX_FAILED_LOGINS lần thì khóa tạm AUTH_LOCKOUT_MINUTES phút.
* Access token ngắn hạn (stateless); refresh token xoay vòng, lưu băm, dùng lại token cũ = thu hồi cả họ.
* Các kết quả "thất bại" (sai mật khẩu, dùng lại token...) cần GHI DB (đếm lần sai, thu hồi) nên service chỉ raise
  SAU KHI transaction đã commit.
"""
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from app.core import tokens
from app.core.errors import (
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
    RateLimited,
    ValidationFailed,
)
from app.core.ids import new_id
from app.core.passwords import PasswordHasher, validate_password
from app.db.models.auth import RefreshToken, User
from app.db.types import utcnow
from app.db.unit_of_work import UnitOfWorkFactory
from app.schemas.auth_schema import AuthResponse, TokenPair, UserOut
from app.schemas.common_schema import Page

log = logging.getLogger("app.services.auth")

VALID_ROLES = ("USER", "ADMIN")
MIN_PASSWORD_LENGTH = 8
INVALID_LOGIN = "Email hoặc mật khẩu không đúng."
INVALID_SESSION = "Phiên đăng nhập không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại."


def to_user_out(user: User) -> UserOut:
    return UserOut(
        user_id=user.id, email=user.email, full_name=user.full_name, roles=list(user.roles or []),
        is_active=bool(user.is_active), created_at=user.created_at, last_login_at=user.last_login_at,
    )


class AuthService:
    def __init__(self, uow_factory: UnitOfWorkFactory, settings, *, hasher: PasswordHasher | None = None,
                 clock: Callable[[], datetime] = utcnow):
        self._uow = uow_factory
        self.s = settings
        self.hasher = hasher or PasswordHasher()
        self._now = clock

    # ---------------- nội bộ ----------------
    def _ensure_can_issue(self) -> None:
        if not tokens.can_issue(self.s):
            raise ConfigurationError(
                "Chưa cấu hình khóa ký JWT: đặt JWT_SECRET (>= 32 ký tự) với JWT_ALGORITHM=HS256, "
                "hoặc JWT_PRIVATE_KEY với RS256."
            )

    async def _issue(self, uow, user: User, *, ip: str | None, user_agent: str | None,
                     family_id: str | None = None) -> tuple[TokenPair, str]:
        now = self._now()
        access, expires_in = tokens.create_access_token(
            self.s, user_id=user.id, roles=user.roles or ["USER"], email=user.email
        )
        raw = tokens.new_refresh_token()
        row = RefreshToken(
            id=new_id("r"), user_id=user.id, family_id=family_id or new_id("fam"),
            token_hash=tokens.hash_refresh_token(raw), created_at=now,
            expires_at=now + timedelta(days=self.s.jwt_refresh_ttl_days),
            ip=ip, user_agent=(user_agent or "")[:255] or None,
        )
        await uow.refresh_tokens.add(row)
        return TokenPair(access_token=access, refresh_token=raw, expires_in=expires_in), row.id

    def _auth_response(self, pair: TokenPair, user: User) -> AuthResponse:
        return AuthResponse(**pair.model_dump(), user=to_user_out(user))

    def _register_failure(self, user: User, now: datetime) -> None:
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= self.s.auth_max_failed_logins:
            user.locked_until = now + timedelta(minutes=self.s.auth_lockout_minutes)
            user.failed_login_count = 0
            log.warning("Khóa tạm tài khoản %s do đăng nhập sai nhiều lần", user.id)

    @staticmethod
    def _locked_error(user: User, now: datetime) -> RateLimited:
        wait = max(1, int((user.locked_until - now).total_seconds()) + 1)
        return RateLimited(
            "Tài khoản tạm khóa do nhập sai mật khẩu nhiều lần. Vui lòng thử lại sau.",
            headers={"Retry-After": str(wait)},
        )

    # ---------------- đăng ký / đăng nhập ----------------
    async def register(self, email: str, password: str, full_name: str | None, *,
                       ip: str | None = None, user_agent: str | None = None) -> AuthResponse:
        if not self.s.auth_registration_enabled:
            raise PermissionDenied("Đăng ký tài khoản mới đang tạm tắt.")
        self._ensure_can_issue()
        problem = validate_password(password, email=email, min_length=MIN_PASSWORD_LENGTH)
        if problem:
            raise ValidationFailed(problem)

        password_hash = await self.hasher.ahash(password)
        now = self._now()
        user = User(
            id=new_id("u"), email=email, password_hash=password_hash, full_name=full_name, roles=["USER"],
            is_active=True, failed_login_count=0, password_changed_at=now, last_login_at=now,
            created_at=now, updated_at=now,
        )
        async with self._uow() as uow:
            if await uow.users.get_by_email(email) is not None:
                raise ConflictError("Email này đã được đăng ký.")
            await uow.users.add(user)
            pair, _ = await self._issue(uow, user, ip=ip, user_agent=user_agent)
            return self._auth_response(pair, user)

    async def login(self, email: str, password: str, *, ip: str | None = None,
                    user_agent: str | None = None) -> AuthResponse:
        self._ensure_can_issue()
        now = self._now()
        outcome = "invalid"
        result: AuthResponse | None = None
        locked_user: User | None = None

        async with self._uow() as uow:
            user = await uow.users.get_by_email(email)
            if user is None:
                outcome = "unknown"
            elif user.locked_until is not None and user.locked_until > now:
                outcome, locked_user = "locked", user
            elif not await self.hasher.averify(password, user.password_hash):
                self._register_failure(user, now)
                outcome = "invalid"
            elif not user.is_active:
                outcome = "disabled"
            else:
                user.failed_login_count = 0
                user.locked_until = None
                user.last_login_at = now
                if self.hasher.needs_rehash(user.password_hash):       # nâng tham số băm một cách âm thầm
                    user.password_hash = await self.hasher.ahash(password)
                pair, _ = await self._issue(uow, user, ip=ip, user_agent=user_agent)
                result = self._auth_response(pair, user)
                outcome = "ok"

        if outcome == "ok" and result is not None:
            return result
        if outcome == "unknown":
            await self.hasher.burn(password)
        if outcome == "locked" and locked_user is not None:
            raise self._locked_error(locked_user, now)
        if outcome == "disabled":
            raise PermissionDenied("Tài khoản đã bị vô hiệu hóa. Vui lòng liên hệ quản trị viên.")
        raise AuthenticationError(INVALID_LOGIN)

    # ---------------- làm mới / thu hồi ----------------
    async def refresh(self, refresh_token: str, *, ip: str | None = None,
                      user_agent: str | None = None) -> AuthResponse:
        self._ensure_can_issue()
        now = self._now()
        result: AuthResponse | None = None

        async with self._uow() as uow:
            row = await uow.refresh_tokens.get_by_hash(tokens.hash_refresh_token(refresh_token))
            if row is None:
                pass
            elif row.revoked_at is not None:
                # Token đã dùng/thu hồi mà vẫn bị đưa ra: có thể đã bị đánh cắp -> thu hồi cả họ token
                await uow.refresh_tokens.revoke_family(row.family_id, now)
                log.warning("Phát hiện dùng lại refresh token (family %s), đã thu hồi cả họ", row.family_id)
            elif row.expires_at <= now:
                pass
            else:
                user = await uow.users.get_by_id(row.user_id)
                if user is None or not user.is_active:
                    await uow.refresh_tokens.revoke_family(row.family_id, now)
                else:
                    row.revoked_at = now
                    pair, new_id_ = await self._issue(uow, user, ip=ip, user_agent=user_agent,
                                                      family_id=row.family_id)
                    row.replaced_by = new_id_
                    result = self._auth_response(pair, user)

        if result is None:
            raise AuthenticationError(INVALID_SESSION)
        return result

    async def logout(self, refresh_token: str) -> None:
        """Thu hồi cả họ token của phiên này. Luôn thành công (token lạ cũng không báo lỗi)."""
        async with self._uow() as uow:
            row = await uow.refresh_tokens.get_by_hash(tokens.hash_refresh_token(refresh_token))
            if row is not None:
                await uow.refresh_tokens.revoke_family(row.family_id, self._now())

    async def logout_all(self, user_id: str) -> None:
        async with self._uow() as uow:
            await uow.refresh_tokens.revoke_all_for_user(user_id, self._now())

    # ---------------- tài khoản của chính mình ----------------
    async def me(self, user_id: str) -> UserOut:
        async with self._uow() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None or not user.is_active:
                raise AuthenticationError(INVALID_SESSION)
            return to_user_out(user)

    async def change_password(self, user_id: str, current_password: str, new_password: str, *,
                              ip: str | None = None, user_agent: str | None = None) -> AuthResponse:
        """Đổi mật khẩu: thu hồi MỌI phiên cũ rồi cấp token mới để thiết bị hiện tại không bị đăng xuất."""
        self._ensure_can_issue()
        now = self._now()
        outcome = "invalid"
        problem: str | None = None
        result: AuthResponse | None = None
        locked_user: User | None = None

        async with self._uow() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None or not user.is_active:
                outcome = "invalid"
            elif user.locked_until is not None and user.locked_until > now:
                outcome, locked_user = "locked", user
            elif not await self.hasher.averify(current_password, user.password_hash):
                self._register_failure(user, now)                    # chống dò mật khẩu cũ bằng access token bị lộ
                outcome = "wrong"
            else:
                problem = validate_password(new_password, email=user.email, min_length=MIN_PASSWORD_LENGTH)
                if problem is None and new_password == current_password:
                    problem = "Mật khẩu mới phải khác mật khẩu hiện tại."
                if problem is not None:
                    outcome = "weak"
                else:
                    user.password_hash = await self.hasher.ahash(new_password)
                    user.password_changed_at = now
                    user.failed_login_count = 0
                    await uow.refresh_tokens.revoke_all_for_user(user.id, now)
                    pair, _ = await self._issue(uow, user, ip=ip, user_agent=user_agent)
                    result = self._auth_response(pair, user)
                    outcome = "ok"

        if outcome == "ok" and result is not None:
            return result
        if outcome == "locked" and locked_user is not None:
            raise self._locked_error(locked_user, now)
        if outcome == "wrong":
            raise ValidationFailed("Mật khẩu hiện tại không đúng.")
        if outcome == "weak":
            raise ValidationFailed(problem or "Mật khẩu mới không hợp lệ.")
        raise AuthenticationError(INVALID_SESSION)

    # ---------------- quản trị người dùng (ADMIN) ----------------
    async def list_users(self, page: int, page_size: int) -> Page[UserOut]:
        async with self._uow() as uow:
            rows, total = await uow.users.list_page((page - 1) * page_size, page_size)
            items = [to_user_out(u) for u in rows]
        return Page[UserOut](items=items, page=page, page_size=page_size, total=total)

    async def set_roles(self, user_id: str, roles: list[str]) -> UserOut:
        wanted = sorted({r.upper() for r in roles} | {"USER"})          # ai cũng là USER; ADMIN là quyền thêm
        if any(r not in VALID_ROLES for r in wanted):
            raise ValidationFailed(f"Vai trò hợp lệ: {', '.join(VALID_ROLES)}.")
        blocked = False
        async with self._uow() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise NotFoundError("Không tìm thấy người dùng.")
            if ("ADMIN" in (user.roles or []) and "ADMIN" not in wanted and user.is_active
                    and await uow.users.count_active_admins() <= 1):
                blocked = True
            else:
                user.roles = wanted
                out = to_user_out(user)
        if blocked:
            raise ConflictError("Không thể gỡ quyền của quản trị viên cuối cùng.")
        return out

    async def set_active(self, actor_id: str, user_id: str, active: bool) -> UserOut:
        if not active and actor_id == user_id:
            raise ConflictError("Không thể tự vô hiệu hóa tài khoản của chính mình.")
        blocked = False
        async with self._uow() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise NotFoundError("Không tìm thấy người dùng.")
            if (not active and user.is_active and "ADMIN" in (user.roles or [])
                    and await uow.users.count_active_admins() <= 1):
                blocked = True
            else:
                user.is_active = active
                if not active:
                    await uow.refresh_tokens.revoke_all_for_user(user.id, self._now())
                else:
                    user.failed_login_count, user.locked_until = 0, None
                out = to_user_out(user)
        if blocked:
            raise ConflictError("Không thể vô hiệu hóa quản trị viên cuối cùng.")
        return out