import json
from datetime import timedelta

from app.db.models.chat import Conversation
from app.db.types import utcnow
from app.rag.types import RAGResult, RAGTrace
from app.schemas.chat_schema import Intent, SourceItem, SourceType
from app.services.history_service import HistoryService, derive_title
from tests.unit.fakes_db import MemoryStore, make_fake_uow_factory
from tests.unit.fakes_redis import FakeRedis


def result(answer="ok", intent=Intent.FAQ_POLICY):
    src = SourceItem(type=SourceType.FAQ, id="faq-1", title="Hủy đơn", snippet="s", url="/faq/1", score=0.9)
    return RAGResult(answer=answer, intent=intent, sources=[src], trace=RAGTrace(model="m", prompt_version="v"))


def make(redis=None, turns=6, tokens=1500):
    store = MemoryStore()
    store.conversations["c_1"] = Conversation(id="c_1", user_id="u1", title=None,
                                             created_at=utcnow(), updated_at=utcnow())
    svc = HistoryService(make_fake_uow_factory(store), redis, max_turns=turns, max_tokens=tokens,
                         count_tokens=len)
    return svc, store


async def test_save_turn_stores_both_messages_in_order_with_sources_and_trace():
    svc, store = make()
    mid = await svc.save_turn("c_1", "Có hủy đơn được không?", result("Được"), request_id="rid-1")
    user_msg, assistant_msg = store.messages
    assert assistant_msg.id == mid and (user_msg.role, assistant_msg.role) == ("user", "assistant")
    assert user_msg.created_at < assistant_msg.created_at          # thứ tự ổn định
    assert assistant_msg.sources[0]["id"] == "faq-1" and assistant_msg.trace["model"] == "m"
    assert assistant_msg.trace["fallback_reason"] is None and assistant_msg.request_id == "rid-1"
    assert store.conversations["c_1"].title == "Có hủy đơn được không?"


async def test_assistant_is_after_user_even_if_user_timestamp_is_in_the_future():
    svc, store = make()
    future = utcnow() + timedelta(seconds=5)
    await svc.save_turn("c_1", "q", result(), user_at=future)
    assert store.messages[0].created_at < store.messages[1].created_at


async def test_recent_returns_chronological_turns_trimmed_by_budget():
    svc, _ = make(turns=2, tokens=1000)
    for i in range(4):
        await svc.save_turn("c_1", f"q{i}", result(f"a{i}"))
    recent = await svc.recent("c_1")
    assert [m["content"] for m in recent] == ["q2", "a2", "q3", "a3"]      # chỉ 2 lượt mới nhất


async def test_cache_is_warmed_on_read_and_written_through_afterwards():
    redis = FakeRedis()
    svc, _ = make(redis)
    await svc.save_turn("c_1", "q0", result("a0"))
    assert "chat:history:c_1" not in redis.data                  # cache nguội: không ghi 2 message lẻ
    assert [m["content"] for m in await svc.recent("c_1")] == ["q0", "a0"]
    assert len(redis.data["chat:history:c_1"]) == 2              # đã nạp từ MySQL
    await svc.save_turn("c_1", "q1", result("a1"))
    cached = [json.loads(x)["content"] for x in redis.data["chat:history:c_1"]]
    assert cached == ["q0", "a0", "q1", "a1"]                    # write-through


async def test_redis_failure_falls_back_to_database():
    svc, _ = make(FakeRedis(fail=True))
    await svc.save_turn("c_1", "q0", result("a0"))
    assert [m["content"] for m in await svc.recent("c_1")] == ["q0", "a0"]


async def test_delete_history_is_owner_only_and_clears_cache():
    from app.core.errors import PermissionDenied
    import pytest

    redis = FakeRedis()
    svc, store = make(redis)
    await svc.save_turn("c_1", "q0", result("a0"))
    await svc.recent("c_1")
    with pytest.raises(PermissionDenied):
        await svc.delete_history(user_id="intruder", conversation_id="c_1")
    await svc.delete_history(user_id="u1", conversation_id="c_1")
    assert store.conversations["c_1"].deleted_at is not None and "chat:history:c_1" not in redis.data


def test_derive_title_collapses_whitespace_and_truncates():
    assert derive_title("  xin   chào \n bạn ") == "xin chào bạn"
    assert len(derive_title("x" * 200)) == 60 and derive_title("x" * 200).endswith("…")
