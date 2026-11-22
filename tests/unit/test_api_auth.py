import time

import jwt

from tests.unit.api_helpers import HS_SECRET, build

GOOD = "Mat-khau-tot-1"


def register(ctx, email="An@ShopMeal.vn", password=GOOD, name="  Nguyễn   An "):
    return ctx.client.post(ctx.url("/auth/register"), json={"email": email, "password": password, "fullName": name})


def login(ctx, email="an@shopmeal.vn", password=GOOD):
    return ctx.client.post(ctx.url("/auth/login"), json={"email": email, "password": password})


def bearer(res) -> dict:
    return {"Authorization": f"Bearer {res.json()['accessToken']}"}


def make_admin(ctx, email="admin@shopmeal.vn"):
    """Đăng ký rồi nâng quyền trực tiếp trong DB (giống scripts.create_admin), đăng nhập lại để token có vai trò ADMIN."""
    register(ctx, email=email)
    user = next(u for u in ctx.store.users.values() if u.email == email)
    user.roles = ["USER", "ADMIN"]
    return login(ctx, email=email)


# ---------------- đăng ký / đăng nhập ----------------
def test_register_returns_user_and_tokens_and_normalizes_input(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    r = register(ctx)
    assert r.status_code == 201
    body = r.json()
    assert body["tokenType"] == "Bearer" and body["expiresIn"] == 1800 and len(body["refreshToken"]) >= 60
    assert body["user"]["email"] == "an@shopmeal.vn" and body["user"]["fullName"] == "Nguyễn An"
    assert body["user"]["roles"] == ["USER"] and body["user"]["userId"].startswith("u_")
    assert "password" not in r.text.lower() and "scrypt" not in r.text            # không bao giờ trả mật khẩu/băm


def test_register_validation_conflict_and_closed_registration(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    assert register(ctx).status_code == 201
    assert register(ctx, email="AN@shopmeal.vn").status_code == 409                 # trùng, không phân biệt hoa thường
    assert register(ctx, email="khong-phai-email").status_code == 422
    weak = register(ctx, email="khac@shopmeal.vn", password="12345678")
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "VALIDATION_ERROR"
    assert register(ctx, email="khac@shopmeal.vn", password="a" * 129).status_code == 422
    assert len(ctx.store.users) == 1

    closed = build(monkeypatch, auth_mode=True, registration=False)
    assert register(closed).status_code == 403


def test_login_me_and_generic_failures(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    register(ctx)
    ok = login(ctx)
    assert ok.status_code == 200
    me = ctx.client.get(ctx.url("/auth/me"), headers=bearer(ok))
    assert me.status_code == 200 and me.json()["email"] == "an@shopmeal.vn"

    wrong = login(ctx, password="sai-mat-khau-1")
    unknown = login(ctx, email="khong-co@shopmeal.vn", password="sai-mat-khau-1")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]    # không lộ email có tồn tại hay không


def test_account_is_locked_after_repeated_failures(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True, max_failed=3)
    register(ctx)
    for _ in range(3):
        assert login(ctx, password="sai-mat-khau-1").status_code == 401
    locked = login(ctx)                                                             # đúng mật khẩu vẫn bị khóa
    assert locked.status_code == 429 and int(locked.headers["Retry-After"]) > 0


def test_auth_endpoints_have_their_own_rate_limit(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True, auth_limit=3)
    codes = [login(ctx, email="x@shopmeal.vn", password="sai-mat-khau-1").status_code for _ in range(5)]
    assert codes == [401, 401, 401, 429, 429]


# ---------------- sử dụng token ----------------
def test_access_token_works_for_chat_and_conversations_belong_to_the_user(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    res = register(ctx)
    reply = ctx.client.post(ctx.url("/chat"), json={"message": "Có được hủy đơn không?"}, headers=bearer(res))
    assert reply.status_code == 200
    user_id = res.json()["user"]["userId"]
    assert ctx.store.conversations[reply.json()["conversationId"]].user_id == user_id
    hist = ctx.client.get(ctx.url(f"/history/{reply.json()['conversationId']}"), headers=bearer(res))
    assert hist.status_code == 200 and hist.json()["total"] == 2


def test_missing_garbage_expired_and_wrong_type_tokens_are_rejected(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    res = register(ctx)
    me = ctx.url("/auth/me")
    assert ctx.client.get(me).status_code == 401
    assert ctx.client.get(me, headers={"Authorization": "Bearer rac-roi"}).status_code == 401
    assert ctx.client.get(me, headers={"Authorization": f"Bearer {res.json()['refreshToken']}"}).status_code == 401

    user_id = res.json()["user"]["userId"]
    base = {"sub": user_id, "iss": "shop-meal-chatbot", "roles": ["USER"]}
    expired = jwt.encode({**base, "typ": "access", "exp": int(time.time()) - 60}, HS_SECRET, algorithm="HS256")
    refresh_typed = jwt.encode({**base, "typ": "refresh", "exp": int(time.time()) + 600}, HS_SECRET, algorithm="HS256")
    wrong_key = jwt.encode({**base, "typ": "access", "exp": int(time.time()) + 600}, "k" * 48, algorithm="HS256")
    for bad in (expired, refresh_typed, wrong_key):
        assert ctx.client.get(me, headers={"Authorization": f"Bearer {bad}"}).status_code == 401


# ---------------- làm mới / đăng xuất ----------------
def test_refresh_rotates_and_reusing_the_old_token_kills_the_session(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    first = register(ctx).json()
    refresh = lambda token: ctx.client.post(ctx.url("/auth/refresh"), json={"refreshToken": token})
    second = refresh(first["refreshToken"])
    assert second.status_code == 200 and second.json()["refreshToken"] != first["refreshToken"]
    assert refresh(first["refreshToken"]).status_code == 401                         # dùng lại token cũ
    assert refresh(second.json()["refreshToken"]).status_code == 401                 # cả họ bị thu hồi
    assert refresh("x" * 40).status_code == 401
    assert refresh("ngan").status_code == 422


def test_logout_and_logout_all(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    a = register(ctx)
    b = login(ctx)
    out = ctx.client.post(ctx.url("/auth/logout"), json={"refreshToken": a.json()["refreshToken"]})
    assert out.status_code == 204
    assert ctx.client.post(ctx.url("/auth/refresh"), json={"refreshToken": a.json()["refreshToken"]}).status_code == 401
    assert ctx.client.post(ctx.url("/auth/logout"), json={"refreshToken": "x" * 40}).status_code == 204    # idempotent

    assert ctx.client.post(ctx.url("/auth/logout-all")).status_code == 401
    assert ctx.client.post(ctx.url("/auth/logout-all"), headers=bearer(b)).status_code == 204
    assert ctx.client.post(ctx.url("/auth/refresh"), json={"refreshToken": b.json()["refreshToken"]}).status_code == 401


def test_change_password_flow(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    res = register(ctx)
    change = lambda current, new: ctx.client.put(ctx.url("/auth/password"), headers=bearer(res),
                                                 json={"currentPassword": current, "newPassword": new})
    assert change("sai-mat-khau-1", "Mat-khau-moi-9").status_code == 422
    assert change(GOOD, "123").status_code == 422
    assert ctx.client.put(ctx.url("/auth/password"), json={"currentPassword": GOOD, "newPassword": "Mat-khau-moi-9"}).status_code == 401

    ok = change(GOOD, "Mat-khau-moi-9")
    assert ok.status_code == 200 and ok.json()["accessToken"]
    assert ctx.client.post(ctx.url("/auth/refresh"), json={"refreshToken": res.json()["refreshToken"]}).status_code == 401
    assert login(ctx).status_code == 401 and login(ctx, password="Mat-khau-moi-9").status_code == 200


# ---------------- phân quyền ----------------
def test_admin_endpoints_require_the_admin_role(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    user = register(ctx)
    url = ctx.url("/admin/users")
    assert ctx.client.get(url).status_code == 401                                    # khách
    forbidden = ctx.client.get(url, headers=bearer(user))
    assert forbidden.status_code == 403 and forbidden.json()["error"]["code"] == "PERMISSION_DENIED"

    admin = make_admin(ctx)
    listing = ctx.client.get(url, headers=bearer(admin))
    assert listing.status_code == 200 and listing.json()["total"] == 2
    assert {u["email"] for u in listing.json()["items"]} == {"an@shopmeal.vn", "admin@shopmeal.vn"}
    assert "password" not in listing.text.lower()


def test_admin_manages_roles_and_status_with_safeguards(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True)
    user = register(ctx)
    user_id = user.json()["user"]["userId"]
    admin = make_admin(ctx)
    admin_id = admin.json()["user"]["userId"]
    h = bearer(admin)

    promoted = ctx.client.patch(ctx.url(f"/admin/users/{user_id}/roles"), headers=h, json={"roles": ["ADMIN"]})
    assert promoted.status_code == 200 and promoted.json()["roles"] == ["ADMIN", "USER"]
    assert ctx.client.patch(ctx.url(f"/admin/users/{user_id}/roles"), headers=h, json={"roles": ["ROOT"]}).status_code == 422
    assert ctx.client.patch(ctx.url("/admin/users/u_khong_co/roles"), headers=h, json={"roles": ["USER"]}).status_code == 404

    assert ctx.client.patch(ctx.url(f"/admin/users/{admin_id}/status"), headers=h, json={"active": False}).status_code == 409
    blocked = ctx.client.patch(ctx.url(f"/admin/users/{user_id}/status"), headers=h, json={"active": False})
    assert blocked.status_code == 200 and blocked.json()["isActive"] is False
    assert login(ctx).status_code == 403                                            # tài khoản bị khóa

    ctx.client.patch(ctx.url(f"/admin/users/{user_id}/status"), headers=h, json={"active": True})
    assert ctx.client.patch(ctx.url(f"/admin/users/{user_id}/roles"), headers=h, json={"roles": ["USER"]}).status_code == 200
    last = ctx.client.patch(ctx.url(f"/admin/users/{admin_id}/roles"), headers=h, json={"roles": ["USER"]})
    assert last.status_code == 409                                                  # admin cuối cùng


class StubIngestion:
    async def start(self, mode):
        from app.schemas.ingestion_schema import IngestionRunResponse
        return IngestionRunResponse(run_id=1, mode=mode, status="RUNNING")


def test_self_issued_admin_token_also_unlocks_ingestion_endpoint(monkeypatch):
    ctx = build(monkeypatch, auth_mode=True, ingestion=StubIngestion())
    user = register(ctx)
    run = lambda headers: ctx.client.post(ctx.url("/admin/ingestion/run"), headers=headers)
    assert run(bearer(user)).status_code == 403
    admin = make_admin(ctx)
    assert run(bearer(admin)).status_code == 202