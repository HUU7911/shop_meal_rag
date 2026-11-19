"""UnitOfWork giả (in-memory) để test services/API mà không cần MySQL. Dùng chung model ORM thật
(khởi tạo đối tượng ORM không cần kết nối DB)."""
from datetime import datetime

from app.db.models.chat import ChatMessage, Conversation, Feedback
from app.db.models.ingestion import IngestionRun
from app.db.types import utcnow


class MemoryStore:
    def __init__(self):
        self.conversations: dict[str, Conversation] = {}
        self.messages: list[ChatMessage] = []
        self.feedback: list[Feedback] = []
        self.runs: dict[int, IngestionRun] = {}
        self.commits = 0


class FakeConversationRepository:
    def __init__(self, store: MemoryStore):
        self.s = store

    async def create(self, conversation: Conversation) -> Conversation:
        now = utcnow()
        conversation.created_at = conversation.created_at or now
        conversation.updated_at = conversation.updated_at or now
        self.s.conversations[conversation.id] = conversation
        return conversation

    async def get_by_id(self, conversation_id: str):
        c = self.s.conversations.get(conversation_id)
        return c if c is not None and c.deleted_at is None else None

    async def list_by_user(self, user_id: str, offset: int = 0, limit: int = 20):
        rows = sorted(
            (c for c in self.s.conversations.values() if c.user_id == user_id and c.deleted_at is None),
            key=lambda c: c.updated_at, reverse=True,
        )
        return rows[offset: offset + limit], len(rows)

    async def touch(self, conversation_id: str, *, title: str | None = None) -> None:
        c = self.s.conversations[conversation_id]
        c.updated_at = utcnow()
        if title is not None and c.title is None:
            c.title = title

    async def soft_delete(self, conversation_id: str) -> bool:
        c = self.s.conversations.get(conversation_id)
        if c is None or c.deleted_at is not None:
            return False
        c.deleted_at = utcnow()
        return True

    async def purge(self, *, soft_deleted_before: datetime, inactive_before: datetime) -> int:
        doomed = [
            c.id for c in self.s.conversations.values()
            if (c.deleted_at and c.deleted_at < soft_deleted_before) or c.updated_at < inactive_before
        ]
        for cid in doomed:
            self.s.messages = [m for m in self.s.messages if m.conversation_id != cid]
            del self.s.conversations[cid]
        return len(doomed)


class FakeMessageRepository:
    def __init__(self, store: MemoryStore):
        self.s = store

    def _ordered(self, conversation_id: str):
        return sorted(
            (m for m in self.s.messages if m.conversation_id == conversation_id),
            key=lambda m: (m.created_at, m.id),
        )

    async def add_many(self, messages: list[ChatMessage]) -> None:
        self.s.messages.extend(messages)

    async def get_by_id(self, message_id: str):
        return next((m for m in self.s.messages if m.id == message_id), None)

    async def list_recent(self, conversation_id: str, limit: int):
        return self._ordered(conversation_id)[-limit:]

    async def list_page(self, conversation_id: str, offset: int, limit: int):
        rows = self._ordered(conversation_id)
        return rows[offset: offset + limit], len(rows)


class FakeFeedbackRepository:
    def __init__(self, store: MemoryStore):
        self.s = store

    async def get_by_message_and_user(self, message_id: str, user_id: str | None):
        return next((f for f in self.s.feedback if f.message_id == message_id and f.user_id == user_id), None)

    async def add(self, feedback: Feedback) -> Feedback:
        self.s.feedback.append(feedback)
        return feedback


class FakeIngestionRepository:
    def __init__(self, store: MemoryStore):
        self.s = store

    async def create_run(self, mode: str) -> IngestionRun:
        run = IngestionRun(id=len(self.s.runs) + 1, mode=mode, status="RUNNING", started_at=utcnow(),
                           added=0, updated=0, deleted=0, skipped=0)
        self.s.runs[run.id] = run
        return run

    async def get_run(self, run_id: int):
        return self.s.runs.get(run_id)

    async def finish_run(self, run_id, *, status, stats=None, error=None, finished_at=None):
        run = self.s.runs[run_id]
        run.status, run.error, run.finished_at = status, error, finished_at or utcnow()
        for k, v in (stats or {}).items():
            setattr(run, k, v)

    async def fail_stale_runs(self, reason: str) -> int:
        stale = [r for r in self.s.runs.values() if r.status == "RUNNING"]
        for r in stale:
            r.status, r.error = "FAILED", reason
        return len(stale)


class FakeUoW:
    def __init__(self, store: MemoryStore):
        self.store = store
        self.conversations = FakeConversationRepository(store)
        self.messages = FakeMessageRepository(store)
        self.feedback = FakeFeedbackRepository(store)
        self.ingestion = FakeIngestionRepository(store)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is None:
            self.store.commits += 1


def make_fake_uow_factory(store: MemoryStore):
    return lambda: FakeUoW(store)

