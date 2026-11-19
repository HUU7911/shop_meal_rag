from tests.unit.api_helpers import INTERNAL_KEY, auth, build


def chat(ctx, text="Có được hủy đơn không?", headers=None, conversation_id=None):
    body = {"message": text}
    if conversation_id:
        body["conversationId"] = conversation_id
    return ctx.client.post(ctx.url("/chat"), json=body, headers=headers or {}).json()


# ---------- quyền sở hữu conversation / history ----------
def test_owner_reads_history_in_order_but_other_users_and_guests_cannot(monkeypatch):
    ctx = build(monkeypatch)
    first = chat(ctx, headers=auth("alice"))
    cid = first["conversationId"]

    ok = ctx.client.get(ctx.url(f"/history/{cid}"), headers=auth("alice"))
    assert ok.status_code == 200
    body = ok.json()
    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    assert body["messages"][1]["messageId"] == first["messageId"] and body["total"] == 2
    assert body["messages"][1]["sources"][0]["id"] == "cancellation_policy"

    bob = ctx.client.get(ctx.url(f"/history/{cid}"), headers=auth("bob"))
    assert bob.status_code == 403 and bob.json()["error"]["code"] == "PERMISSION_DENIED"
    assert ctx.client.get(ctx.url(f"/history/{cid}")).status_code == 401           # khách cần đăng nhập
    assert ctx.client.get(ctx.url("/history/c_missing"), headers=auth("alice")).status_code == 404


def test_user_cannot_continue_someone_elses_conversation(monkeypatch):
    ctx = build(monkeypatch)
    cid = chat(ctx, headers=auth("alice"))["conversationId"]
    r = ctx.client.post(ctx.url("/chat"), json={"conversationId": cid, "message": "hi"}, headers=auth("bob"))
    assert r.status_code == 403
    r = ctx.client.post(ctx.url("/chat"), json={"conversationId": cid, "message": "hi"})   # khách
    assert r.status_code == 403
    assert len(ctx.store.messages) == 2                                           # không có gì bị ghi thêm


def test_guest_conversation_is_not_readable_by_logged_in_users(monkeypatch):
    ctx = build(monkeypatch)
    cid = chat(ctx)["conversationId"]
    assert ctx.client.get(ctx.url(f"/history/{cid}"), headers=auth("alice")).status_code == 403


def test_history_pagination_uses_camel_case_page_size(monkeypatch):
    ctx = build(monkeypatch)
    cid = chat(ctx, headers=auth("alice"))["conversationId"]
    chat(ctx, "Còn đổi địa chỉ?", headers=auth("alice"), conversation_id=cid)
    page = ctx.client.get(ctx.url(f"/history/{cid}?page=2&pageSize=2"), headers=auth("alice")).json()
    assert page["page"] == 2 and page["pageSize"] == 2 and page["total"] == 4
    assert [m["content"] for m in page["messages"]][0] == "Còn đổi địa chỉ?"


def test_delete_history_soft_deletes_for_owner_only(monkeypatch):
    ctx = build(monkeypatch)
    cid = chat(ctx, headers=auth("alice"))["conversationId"]
    assert ctx.client.delete(ctx.url(f"/history/{cid}"), headers=auth("bob")).status_code == 403
    assert ctx.client.delete(ctx.url(f"/history/{cid}"), headers=auth("alice")).status_code == 204
    assert ctx.client.get(ctx.url(f"/history/{cid}"), headers=auth("alice")).status_code == 404
    assert ctx.store.conversations[cid].deleted_at is not None                    # soft delete, dữ liệu còn


def test_conversations_create_and_list_are_scoped_to_user(monkeypatch):
    ctx = build(monkeypatch)
    created = ctx.client.post(ctx.url("/conversations"), headers=auth("alice"))
    assert created.status_code == 201 and created.json()["conversationId"].startswith("c_")
    chat(ctx, headers=auth("alice"))
    chat(ctx, headers=auth("bob"))
    mine = ctx.client.get(ctx.url("/conversations"), headers=auth("alice")).json()
    assert mine["total"] == 2 and len(mine["items"]) == 2
    assert ctx.client.get(ctx.url("/conversations")).status_code == 401
    assert ctx.client.post(ctx.url("/conversations")).status_code == 401


def test_conversation_title_comes_from_first_question(monkeypatch):
    ctx = build(monkeypatch)
    cid = chat(ctx, "Có được hủy đơn không?", headers=auth("alice"))["conversationId"]
    chat(ctx, "Câu hỏi khác", headers=auth("alice"), conversation_id=cid)
    assert ctx.store.conversations[cid].title == "Có được hủy đơn không?"


# ---------- feedback ----------
def feedback(ctx, cid, mid, headers, rating="NEGATIVE", reason="INACCURATE"):
    return ctx.client.post(ctx.url("/feedback"), headers=headers, json={
        "conversationId": cid, "messageId": mid, "rating": rating, "reason": reason, "comment": "Giá không đúng"})


def test_feedback_only_for_own_assistant_messages(monkeypatch):
    ctx = build(monkeypatch)
    first = chat(ctx, headers=auth("alice"))
    cid, mid = first["conversationId"], first["messageId"]

    ok = feedback(ctx, cid, mid, auth("alice"))
    assert ok.status_code == 200 and ok.json()["accepted"] is True and ok.json()["feedbackId"].startswith("f_")
    assert feedback(ctx, cid, mid, auth("bob")).status_code == 403
    assert feedback(ctx, cid, mid, {}).status_code == 401
    assert feedback(ctx, cid, "m_missing", auth("alice")).status_code == 404
    assert feedback(ctx, "c_other", mid, auth("alice")).status_code == 404         # message không thuộc conversation đó
    user_msg = next(m for m in ctx.store.messages if m.role == "user")
    assert feedback(ctx, cid, user_msg.id, auth("alice")).status_code == 422       # không đánh giá câu hỏi của chính mình


def test_resubmitting_feedback_updates_instead_of_duplicating(monkeypatch):
    ctx = build(monkeypatch)
    first = chat(ctx, headers=auth("alice"))
    cid, mid = first["conversationId"], first["messageId"]
    a = feedback(ctx, cid, mid, auth("alice")).json()["feedbackId"]
    b = feedback(ctx, cid, mid, auth("alice"), rating="POSITIVE", reason="OTHER").json()["feedbackId"]
    assert a == b and len(ctx.store.feedback) == 1
    assert ctx.store.feedback[0].rating == "POSITIVE" and ctx.store.feedback[0].reason is None   # reason chỉ cho NEGATIVE


def test_feedback_validates_enums_and_comment_length(monkeypatch):
    ctx = build(monkeypatch)
    first = chat(ctx, headers=auth("alice"))
    bad = ctx.client.post(ctx.url("/feedback"), headers=auth("alice"), json={
        "conversationId": first["conversationId"], "messageId": first["messageId"], "rating": "MEH"})
    assert bad.status_code == 422
    long = ctx.client.post(ctx.url("/feedback"), headers=auth("alice"), json={
        "conversationId": first["conversationId"], "messageId": first["messageId"],
        "rating": "NEGATIVE", "comment": "x" * 1001})
    assert long.status_code == 422


# ---------- admin ----------
class StubIngestion:
    def __init__(self):
        self.modes = []

    async def start(self, mode):
        from app.schemas.ingestion_schema import IngestionRunResponse
        self.modes.append(mode)
        return IngestionRunResponse(run_id=7, mode=mode, status="RUNNING")


def test_admin_endpoint_requires_admin_role_or_internal_key(monkeypatch):
    stub = StubIngestion()
    ctx = build(monkeypatch, ingestion=stub)
    url = ctx.url("/admin/ingestion/run?mode=full")
    assert ctx.client.post(url).status_code == 403                                    # khách
    assert ctx.client.post(url, headers=auth("alice")).status_code == 403             # user thường
    assert ctx.client.post(url, headers={"X-Internal-Key": "wrong"}).status_code == 403
    assert ctx.client.post(url, headers={"X-Internal-Key": ""}).status_code == 403
    assert stub.modes == []

    via_key = ctx.client.post(url, headers={"X-Internal-Key": INTERNAL_KEY})
    assert via_key.status_code == 202 and via_key.json() == {
        "runId": 7, "mode": "full", "status": "RUNNING", "startedAt": None, "finishedAt": None,
        "added": 0, "updated": 0, "deleted": 0, "skipped": 0, "error": None}
    via_role = ctx.client.post(ctx.url("/admin/ingestion/run"), headers=auth("root", roles=["ROLE_ADMIN"]))
    assert via_role.status_code == 202 and stub.modes == ["full", "incremental"]
    assert ctx.client.post(ctx.url("/admin/ingestion/run?mode=drop"), headers={"X-Internal-Key": INTERNAL_KEY}).status_code == 422


# ---------- health ----------
class StubHealth:
    def __init__(self, status):
        self.status = status

    async def check_all(self):
        return {"status": self.status, "checks": {"mysql": "ok"}}


def test_liveness_is_always_ok_and_readiness_maps_status_to_http_code(monkeypatch):
    ctx = build(monkeypatch, health=StubHealth("unavailable"))
    assert ctx.client.get(ctx.url("/health")).json() == {"status": "ok"}
    assert ctx.client.get(ctx.url("/health/ready")).status_code == 503
    for status in ("ok", "degraded"):
        ctx = build(monkeypatch, health=StubHealth(status))
        assert ctx.client.get(ctx.url("/health/ready")).status_code == 200
