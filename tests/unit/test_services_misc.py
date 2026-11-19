import asyncio

import pytest

from app.core.errors import ConflictError
from app.services.health_service import HealthService
from app.services.ingestion_service import IngestionService
from tests.unit.fakes_db import MemoryStore, make_fake_uow_factory


# ---------- IngestionService ----------
async def test_ingestion_runs_in_background_and_records_stats():
    store = MemoryStore()
    release = asyncio.Event()

    async def runner(mode):
        await release.wait()
        return {"added": 3, "updated": 1, "deleted": 0, "skipped": 9, "status": "success"}

    svc = IngestionService(make_fake_uow_factory(store), runner=runner)
    started = await svc.start("incremental")
    assert started.status == "RUNNING"
    with pytest.raises(ConflictError):                       # đang chạy: không cho chạy chồng
        await svc.start("full")

    release.set()
    await svc._task
    run = await svc.get_run(started.run_id)
    assert run.status == "COMPLETED" and (run.added, run.updated, run.skipped) == (3, 1, 9)
    assert (await svc.start("full")).run_id == started.run_id + 1       # xong rồi thì chạy lại được
    await svc.aclose()


async def test_ingestion_failure_is_recorded_and_lock_released():
    store = MemoryStore()

    async def runner(mode):
        raise RuntimeError("Qdrant sập")

    svc = IngestionService(make_fake_uow_factory(store), runner=runner)
    started = await svc.start("full")
    await svc._task
    run = await svc.get_run(started.run_id)
    assert run.status == "FAILED" and "Qdrant sập" in run.error
    await svc.start("full")                                    # lock đã được nhả
    await svc.aclose()


async def test_stale_running_runs_are_marked_failed_on_startup():
    store = MemoryStore()
    svc = IngestionService(make_fake_uow_factory(store), runner=lambda m: None)
    async with make_fake_uow_factory(store)() as uow:
        await uow.ingestion.create_run("full")
    assert await svc.recover() == 1
    assert store.runs[1].status == "FAILED"


# ---------- HealthService ----------
def test_overall_status_rules():
    ok = {"mysql": "ok", "redis": "ok", "qdrant": "ok", "llm": "configured"}
    assert HealthService.overall_status(ok, rag_enabled=True) == "ok"
    assert HealthService.overall_status({**ok, "mysql": "down"}, rag_enabled=False) == "unavailable"
    assert HealthService.overall_status({**ok, "qdrant": "down"}, rag_enabled=True) == "unavailable"
    assert HealthService.overall_status({**ok, "qdrant": "down"}, rag_enabled=False) == "degraded"
    assert HealthService.overall_status({**ok, "redis": "down"}, rag_enabled=True) == "degraded"
    assert HealthService.overall_status({**ok, "llm": "misconfigured"}, rag_enabled=True) == "degraded"
    assert HealthService.overall_status({**ok, "llm": "disabled"}, rag_enabled=True) == "ok"


# ---------- purge ----------
async def test_purge_removes_expired_and_soft_deleted_conversations():
    from datetime import timedelta

    from app.db.models.chat import ChatMessage, Conversation
    from app.db.types import utcnow

    store = MemoryStore()
    now = utcnow()
    store.conversations = {
        "old": Conversation(id="old", user_id="u", updated_at=now - timedelta(days=100)),
        "gone": Conversation(id="gone", user_id="u", updated_at=now, deleted_at=now - timedelta(days=10)),
        "fresh": Conversation(id="fresh", user_id="u", updated_at=now),
    }
    store.messages = [ChatMessage(id=f"m-{c}", conversation_id=c, role="user", content="x", created_at=now)
                      for c in store.conversations]
    async with make_fake_uow_factory(store)() as uow:
        purged = await uow.conversations.purge(soft_deleted_before=now - timedelta(days=7),
                                               inactive_before=now - timedelta(days=90))
    assert purged == 2 and list(store.conversations) == ["fresh"] and [m.id for m in store.messages] == ["m-fresh"]
