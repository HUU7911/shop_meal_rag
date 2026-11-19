import json

from app.rag.types import RAGEvent, RAGResult, RAGTrace
from app.schemas.chat_schema import Intent, SourceItem, SourceType
from app.services.mock_rag_engine import MockRAGEngine
from tests.unit.api_helpers import auth, build, forged_token


class SpyRAG(MockRAGEngine):
    def __init__(self):
        super().__init__()
        self.requests = []

    async def invoke(self, request):
        self.requests.append(request)
        return await super().invoke(request)


class LeakyOrderRAG:
    """Mô phỏng RAGEngine bị lỗi: trả dữ liệu đơn hàng cho cả khách."""

    async def invoke(self, request):
        src = SourceItem(type=SourceType.ORDER, id="123", title="Đơn #123")
        return RAGResult("Đơn #123 đang được giao", Intent.ORDER_STATUS, [src], RAGTrace(model="x"), None)

    async def stream(self, request):
        yield RAGEvent("done", await self.invoke(request))


class FailingStreamRAG:
    async def invoke(self, request):
        raise AssertionError("không dùng")

    async def stream(self, request):
        yield RAGEvent("token", "Xin ")
        yield RAGEvent("error", "LLM sập")


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_guest_can_chat_and_response_has_ids_sources_and_request_id(monkeypatch):
    ctx = build(monkeypatch)
    r = ctx.client.post(ctx.url("/chat"), json={"message": "Có được hủy đơn không?"})
    assert r.status_code == 200 and r.headers["X-Request-ID"]
    body = r.json()
    assert body["conversationId"].startswith("c_") and body["messageId"].startswith("m_")
    assert body["intent"] == "FAQ_POLICY" and body["sources"][0]["type"] == "POLICY"
    assert len(ctx.store.messages) == 2


def test_second_turn_reuses_conversation_and_sends_history_to_rag(monkeypatch):
    spy = SpyRAG()
    ctx = build(monkeypatch, rag_engine=spy)
    first = ctx.client.post(ctx.url("/chat"), json={"message": "Có được hủy đơn không?"}).json()
    ctx.client.post(ctx.url("/chat"), json={"conversationId": first["conversationId"], "message": "Còn đổi địa chỉ?"})
    assert [t.role for t in spy.requests[1].history] == ["user", "assistant"]
    assert spy.requests[1].history[0].content == "Có được hủy đơn không?"
    assert len(ctx.store.conversations) == 1


def test_guest_asking_about_orders_is_told_to_log_in(monkeypatch):
    ctx = build(monkeypatch)
    body = ctx.client.post(ctx.url("/chat"), json={"message": "Đơn hàng #123 đang ở đâu?"}).json()
    assert body["intent"] == "ORDER_STATUS" and body["metadata"]["fallback"] == "LOGIN_REQUIRED"
    assert body["sources"] == []


def test_guest_never_receives_order_data_even_if_rag_leaks_it(monkeypatch):
    ctx = build(monkeypatch, rag_engine=LeakyOrderRAG())
    body = ctx.client.post(ctx.url("/chat"), json={"message": "đơn của tôi"}).json()
    assert "123" not in body["answer"] and body["sources"] == []
    assert body["metadata"]["fallback"] == "LOGIN_REQUIRED"


def test_logged_in_user_token_is_forwarded_to_rag_and_guest_token_is_not(monkeypatch):
    spy = SpyRAG()
    ctx = build(monkeypatch, rag_engine=spy)
    headers = auth("user-1")
    ctx.client.post(ctx.url("/chat"), json={"message": "Đơn hàng #123 đâu?"}, headers=headers)
    ctx.client.post(ctx.url("/chat"), json={"message": "Đơn hàng #123 đâu?"})
    logged_in, guest = spy.requests
    assert logged_in.user.user_id == "user-1" and logged_in.user.token == headers["Authorization"][7:]
    assert guest.user.is_guest and guest.user.token is None


def test_invalid_or_forged_token_is_rejected_even_when_guests_are_allowed(monkeypatch):
    ctx = build(monkeypatch)
    r = ctx.client.post(ctx.url("/chat"), json={"message": "hi"},
                        headers={"Authorization": f"Bearer {forged_token()}"})
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTHENTICATION_ERROR"
    assert ctx.client.post(ctx.url("/chat"), json={"message": "hi"},
                           headers={"Authorization": "Bearer not-a-jwt"}).status_code == 401
    assert ctx.client.post(ctx.url("/chat"), json={"message": "hi"},
                           headers={"Authorization": "Basic abc"}).status_code == 401


def test_expired_token_is_rejected(monkeypatch):
    ctx = build(monkeypatch)
    r = ctx.client.post(ctx.url("/chat"), json={"message": "hi"}, headers=auth(expires_in=-10))
    assert r.status_code == 401


def test_guests_blocked_when_not_allowed(monkeypatch):
    ctx = build(monkeypatch, allow_guest=False)
    assert ctx.client.post(ctx.url("/chat"), json={"message": "hi"}).status_code == 401
    assert ctx.client.post(ctx.url("/chat"), json={"message": "hi"}, headers=auth()).status_code == 200


def test_message_length_and_blank_are_validated_with_standard_error_body(monkeypatch):
    ctx = build(monkeypatch, max_len=50)
    too_long = ctx.client.post(ctx.url("/chat"), json={"message": "x" * 51})
    assert too_long.status_code == 422
    err = too_long.json()["error"]
    assert err["code"] == "VALIDATION_ERROR" and err["requestId"] == too_long.headers["X-Request-ID"]
    assert ctx.store.messages == []                                          # lượt không hợp lệ không được lưu
    assert ctx.client.post(ctx.url("/chat"), json={"message": "x" * 50}).status_code == 200
    assert ctx.client.post(ctx.url("/chat"), json={"message": "   "}).status_code == 422
    assert ctx.client.post(ctx.url("/chat"), json={}).status_code == 422
    assert len(ctx.store.messages) == 2                                      # chỉ lượt hợp lệ được lưu


def test_validation_error_does_not_echo_user_input(monkeypatch):
    ctx = build(monkeypatch, max_len=5)
    r = ctx.client.post(ctx.url("/chat"), json={"message": "số thẻ 4111111111111111"})
    assert "4111" not in r.text


def test_rate_limit_returns_429_with_retry_after(monkeypatch):
    ctx = build(monkeypatch, rate_limit=2)
    codes = [ctx.client.post(ctx.url("/chat"), json={"message": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = ctx.client.post(ctx.url("/chat"), json={"message": "hi"})
    assert r.json()["error"]["code"] == "RATE_LIMITED" and int(r.headers["Retry-After"]) > 0


def test_rate_limit_is_per_user(monkeypatch):
    ctx = build(monkeypatch, rate_limit=1)
    assert ctx.client.post(ctx.url("/chat"), json={"message": "hi"}, headers=auth("a")).status_code == 200
    assert ctx.client.post(ctx.url("/chat"), json={"message": "hi"}, headers=auth("b")).status_code == 200
    assert ctx.client.post(ctx.url("/chat"), json={"message": "hi"}, headers=auth("a")).status_code == 429


def test_unknown_route_uses_standard_error_body(monkeypatch):
    ctx = build(monkeypatch)
    r = ctx.client.get(ctx.url("/nope"))
    assert r.status_code == 404 and r.json()["error"]["code"] == "NOT_FOUND" and r.json()["error"]["requestId"]


def test_incoming_request_id_is_echoed_and_garbage_is_replaced(monkeypatch):
    ctx = build(monkeypatch)
    ok = ctx.client.get(ctx.url("/health"), headers={"X-Request-ID": "trace-123"})
    assert ok.headers["X-Request-ID"] == "trace-123"
    bad = ctx.client.get(ctx.url("/health"), headers={"X-Request-ID": "bad id\twith spaces!"})
    assert bad.headers["X-Request-ID"] != "bad id\twith spaces!" and len(bad.headers["X-Request-ID"]) == 32


def test_stream_emits_token_sources_done_and_persists_the_turn(monkeypatch):
    ctx = build(monkeypatch)
    r = ctx.client.post(ctx.url("/chat/stream"), json={"message": "Có được hủy đơn không?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    names = [n for n, _ in events]
    assert names[0] == "token" and names[-2:] == ["sources", "done"]
    done = events[-1][1]
    assert done["messageId"].startswith("m_") and done["conversationId"].startswith("c_")
    streamed = "".join(d["text"] for n, d in events if n == "token").strip()
    assert streamed == done["answer"] and len(ctx.store.messages) == 2


def test_stream_failure_midway_emits_error_and_saves_nothing(monkeypatch):
    ctx = build(monkeypatch, rag_engine=FailingStreamRAG())
    r = ctx.client.post(ctx.url("/chat/stream"), json={"message": "hi"})
    events = parse_sse(r.text)
    assert events[-1][0] == "error" and events[-1][1]["code"] == "GENERATION_ERROR"
    assert "done" not in [n for n, _ in events] and ctx.store.messages == []


def test_stream_pre_flight_errors_are_real_http_statuses(monkeypatch):
    ctx = build(monkeypatch)
    mine = ctx.client.post(ctx.url("/chat"), json={"message": "hi"}, headers=auth("owner")).json()
    r = ctx.client.post(ctx.url("/chat/stream"),
                        json={"conversationId": mine["conversationId"], "message": "hi"}, headers=auth("intruder"))
    assert r.status_code == 403
    r = ctx.client.post(ctx.url("/chat/stream"), json={"conversationId": "c_missing", "message": "hi"})
    assert r.status_code == 404
