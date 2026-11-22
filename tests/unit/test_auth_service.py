from datetime import timedelta

import jwt
import pytest

from app.core import tokens
from app.core.config import Settings
from app.core.errors import (
    AuthenticationError,
    ConfigurationError,
    ConflictError,
    NotFoundError,
    PermissionDenied,
    RateLimited,
    ValidationFailed,
)
from app.core.passwords import PasswordHasher
from app.db.types import utcnow
from app.services.auth_service import INVALID_LOGIN, AuthService
from tests.unit.fakes_db import MemoryStore, make_fake_uow_factory

SECRET = "s" * 48
FAST = PasswordHasher(n=2**4, r=1, p=1)
GOOD = "Mat-khau-tot-1"


class Clock:
    def __init__(self):
        self.now = utcnow()

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += timedelta(**kw)


def make(**over):
    config = dict(jwt_algorithm="HS256", jwt_secret=SECRET, jwt_issuer="shop-meal-chatbot", jwt_access_ttl_minutes=30,
                  jwt_refresh_ttl_days=14, auth_max_failed_logins=3, auth_lockout_minutes=15,
                  auth_registration_enabled=True)
    config.update(over)
    settings = Settings(_env_file=None, **config)
    store, clock = MemoryStore(), Clock()
    service = AuthService(make_fake_uow_factory(store), settings, hasher=FAST, clock=clock)
    return service, store, clock


def claims_of(token: str) -> dict:
    return jwt.decode(token, SECRET, algorithms=["HS256"], issuer="shop-meal-chatbot")


async def signup(service, email="an@shopmeal.vn", password=GOOD, name="An"):
    return await service.register(email, password, name, ip="1.2.3.4", user_agent="pytest")


# ---------------- đăng ký ----------------
async def test_register_creates_a_hashed_user_with_role_user_and_logs_in():
    service, store, _ = make()
    res = await signup(service)
    user = store.users[res.user.user_id]
    assert user.roles == ["USER"] and user.password_hash.startswith("scrypt$") and GOOD not in user.password_hash
    claims = claims_of(res.access_token)
    assert claims["sub"] == user.id and claims["roles"] == ["USER"] and claims["typ"] == "access"
    assert res.token_type == "Bearer" and res.expires_in == 1800 and len(res.refresh_token) >= 60
    assert len(store.refresh_tokens) == 1 and store.refresh_tokens[0].token_hash != res.refresh_token   # chỉ lưu băm
    assert store.refresh_tokens[0].ip == "1.2.3.4" and store.refresh_tokens[0].user_agent == "pytest"


async def test_register_rejects_duplicate_email_weak_password_and_closed_registration():
    service, store, _ = make()
    await signup(service)
    with pytest.raises(ConflictError):
        await signup(service)
    for weak in ("short1", "password", "12345678"):
        with pytest.raises(ValidationFailed):
            await signup(service, email="khac@shopmeal.vn", password=weak)
    assert len(store.users) == 1

    closed, _, _ = make(auth_registration_enabled=False)
    with pytest.raises(PermissionDenied):
        await signup(closed)


async def test_service_refuses_to_run_without_a_signing_key():
    service, _, _ = make(jwt_secret="ngắn")
    with pytest.raises(ConfigurationError):
        await signup(service)


# ---------------- đăng nhập ----------------
async def test_login_success_resets_counters_and_unknown_email_gives_the_same_message():
    service, store, _ = make()
    await signup(service)
    user = next(iter(store.users.values()))
    user.failed_login_count = 2
    res = await service.login("an@shopmeal.vn", GOOD)
    assert res.user.email == "an@shopmeal.vn" and user.failed_login_count == 0 and user.last_login_at is not None

    with pytest.raises(AuthenticationError) as wrong_pw:
        await service.login("an@shopmeal.vn", "sai-mat-khau-1")
    with pytest.raises(AuthenticationError) as unknown:
        await service.login("khong-co@shopmeal.vn", "sai-mat-khau-1")
    assert str(wrong_pw.value) == str(unknown.value) == INVALID_LOGIN          # không lộ email nào tồn tại


async def test_failed_attempts_persist_and_lock_the_account_then_unlock_by_time():
    service, store, clock = make()
    await signup(service)
    for _ in range(3):
        with pytest.raises(AuthenticationError):
            await service.login("an@shopmeal.vn", "sai-mat-khau-1")
    assert next(iter(store.users.values())).locked_until is not None          # đã COMMIT dù request báo lỗi

    with pytest.raises(RateLimited) as locked:                                # đúng mật khẩu vẫn bị khóa
        await service.login("an@shopmeal.vn", GOOD)
    assert int(locked.value.headers["Retry-After"]) > 0

    clock.advance(minutes=16)
    assert (await service.login("an@shopmeal.vn", GOOD)).access_token


async def test_disabled_user_cannot_login_but_wrong_password_stays_generic():
    service, store, _ = make()
    await signup(service)
    next(iter(store.users.values())).is_active = False
    with pytest.raises(PermissionDenied):
        await service.login("an@shopmeal.vn", GOOD)
    with pytest.raises(AuthenticationError):
        await service.login("an@shopmeal.vn", "sai-mat-khau-1")


async def test_old_password_hash_parameters_are_upgraded_on_login():
    service, store, _ = make()
    await signup(service)
    user = next(iter(store.users.values()))
    user.password_hash = PasswordHasher(n=2**3, r=1, p=1).hash(GOOD)           # băm theo tham số cũ
    await service.login("an@shopmeal.vn", GOOD)
    assert user.password_hash.startswith("scrypt$16$1$1$") and FAST.verify(GOOD, user.password_hash)


# ---------------- làm mới / thu hồi ----------------
async def test_refresh_rotates_tokens_and_reuse_revokes_the_whole_family():
    service, store, _ = make()
    first = await signup(service)
    second = await service.refresh(first.refresh_token)
    assert second.refresh_token != first.refresh_token and second.access_token
    old_row = next(t for t in store.refresh_tokens if t.revoked_at is not None)
    assert old_row.replaced_by is not None

    with pytest.raises(AuthenticationError):                                   # dùng lại token cũ = nghi bị đánh cắp
        await service.refresh(first.refresh_token)
    with pytest.raises(AuthenticationError):                                   # token mới của cùng họ cũng bị thu hồi
        await service.refresh(second.refresh_token)
    assert all(t.revoked_at is not None for t in store.refresh_tokens)


async def test_refresh_rejects_unknown_expired_and_deactivated():
    service, store, clock = make()
    with pytest.raises(AuthenticationError):
        await service.refresh("x" * 60)

    res = await signup(service)
    clock.advance(days=15)
    with pytest.raises(AuthenticationError):
        await service.refresh(res.refresh_token)

    res2 = await service.login("an@shopmeal.vn", GOOD)
    next(iter(store.users.values())).is_active = False
    with pytest.raises(AuthenticationError):
        await service.refresh(res2.refresh_token)
    row = next(t for t in store.refresh_tokens if t.token_hash == tokens.hash_refresh_token(res2.refresh_token))
    assert row.revoked_at is not None                                          # họ token bị thu hồi


async def test_refresh_reads_current_roles_from_the_database():
    service, store, _ = make()
    res = await signup(service)
    next(iter(store.users.values())).roles = ["USER", "ADMIN"]
    refreshed = await service.refresh(res.refresh_token)
    assert claims_of(refreshed.access_token)["roles"] == ["USER", "ADMIN"]


async def test_logout_revokes_the_session_and_is_idempotent():
    service, _, _ = make()
    res = await signup(service)
    await service.logout(res.refresh_token)
    await service.logout(res.refresh_token)
    await service.logout("khong-ton-tai" * 5)                                   # không ném lỗi
    with pytest.raises(AuthenticationError):
        await service.refresh(res.refresh_token)


async def test_logout_all_revokes_every_device():
    service, _, _ = make()
    a = await signup(service)
    b = await service.login("an@shopmeal.vn", GOOD)
    await service.logout_all(a.user.user_id)
    for token in (a.refresh_token, b.refresh_token):
        with pytest.raises(AuthenticationError):
            await service.refresh(token)


# ---------------- tài khoản của chính mình ----------------
async def test_me_returns_the_user_and_rejects_inactive():
    service, store, _ = make()
    res = await signup(service)
    assert (await service.me(res.user.user_id)).email == "an@shopmeal.vn"
    next(iter(store.users.values())).is_active = False
    with pytest.raises(AuthenticationError):
        await service.me(res.user.user_id)


async def test_change_password_revokes_old_sessions_and_issues_a_fresh_pair():
    service, _, _ = make()
    res = await signup(service)
    uid = res.user.user_id
    new = await service.change_password(uid, GOOD, "Mat-khau-moi-9")
    with pytest.raises(AuthenticationError):
        await service.refresh(res.refresh_token)                                # phiên cũ bị thu hồi
    assert (await service.refresh(new.refresh_token)).access_token              # phiên mới dùng được
    with pytest.raises(AuthenticationError):
        await service.login("an@shopmeal.vn", GOOD)
    assert (await service.login("an@shopmeal.vn", "Mat-khau-moi-9")).access_token


async def test_change_password_validations_and_brute_force_protection():
    service, store, _ = make()
    res = await signup(service)
    uid = res.user.user_id
    with pytest.raises(ValidationFailed):
        await service.change_password(uid, GOOD, GOOD)                          # trùng mật khẩu cũ
    with pytest.raises(ValidationFailed):
        await service.change_password(uid, GOOD, "123")                         # quá yếu
    for _ in range(3):
        with pytest.raises(ValidationFailed):
            await service.change_password(uid, "sai-mat-khau-1", "Mat-khau-moi-9")
    with pytest.raises(RateLimited):                                            # sai quá nhiều lần: khóa
        await service.change_password(uid, GOOD, "Mat-khau-moi-9")
    assert next(iter(store.users.values())).password_hash                       # mật khẩu không bị đổi


# ---------------- quản trị ----------------
async def two_users(service, store):
    admin = await signup(service, "admin@shopmeal.vn", GOOD, "Quản trị")
    store.users[admin.user.user_id].roles = ["USER", "ADMIN"]
    user = await signup(service, "an@shopmeal.vn", GOOD, "An")
    return admin.user.user_id, user.user.user_id


async def test_admin_can_grant_and_revoke_admin_but_not_remove_the_last_one():
    service, store, _ = make()
    admin_id, user_id = await two_users(service, store)

    assert (await service.set_roles(user_id, ["ADMIN"])).roles == ["ADMIN", "USER"]
    assert (await service.set_roles(user_id, ["USER"])).roles == ["USER"]
    await service.set_roles(user_id, ["ADMIN"])
    await service.set_roles(admin_id, ["USER"])                                 # còn một admin khác nên được phép
    with pytest.raises(ConflictError):                                          # admin cuối cùng
        await service.set_roles(user_id, ["USER"])
    with pytest.raises(NotFoundError):
        await service.set_roles("u_khong_co", ["ADMIN"])


async def test_set_active_protects_self_and_last_admin_and_revokes_sessions():
    service, store, _ = make()
    admin_id, user_id = await two_users(service, store)

    with pytest.raises(ConflictError):
        await service.set_active(admin_id, admin_id, False)                     # không tự khóa mình
    with pytest.raises(ConflictError):
        await service.set_active(user_id, admin_id, False)                      # admin cuối cùng

    victim = await service.login("an@shopmeal.vn", GOOD)
    out = await service.set_active(admin_id, user_id, False)
    assert out.is_active is False
    with pytest.raises(AuthenticationError):
        await service.refresh(victim.refresh_token)
    with pytest.raises(PermissionDenied):
        await service.login("an@shopmeal.vn", GOOD)

    store.users[user_id].locked_until = utcnow() + timedelta(hours=1)
    assert (await service.set_active(admin_id, user_id, True)).is_active is True
    assert store.users[user_id].locked_until is None and (await service.login("an@shopmeal.vn", GOOD)).access_token


async def test_list_users_is_paginated():
    service, store, _ = make()
    await two_users(service, store)
    page = await service.list_users(1, 1)
    assert page.total == 2 and len(page.items) == 1 and page.page_size == 1