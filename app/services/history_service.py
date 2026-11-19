"""Đọc/ghi lịch sử. Redis cache N lượt gần nhất; MySQL là nguồn sự thật.

Cắt lịch sử theo token budget (HISTORY_MAX_TOKENS), ưu tiên giữ các lượt mới nhất.

Cache: Redis list `chat:history:{conversation_id}` (JSON {role, content}), write-through KHI KEY ĐÃ TỒN TẠI
(nếu chưa có key mà chỉ đẩy 2 message mới vào thì cache sẽ thiếu các message cũ). Redis lỗi -> bỏ qua cache,
đọc thẳng MySQL (docs/ARCHITECTURE.md §5).
"""
import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.ids import new_id
from app.db.models.chat import ChatMessage
from app.db.types import utcnow
from app.db.unit_of_work import UnitOfWorkFactory
from app.rag.utils import estimate_tokens
from app.schemas.chat_schema import Intent, SourceItem
from app.schemas.history_schema import ConversationHistoryResponse, MessageItem, Role
from app.services.chat_mapper import trace_to_dict
from app.services.conversation_service import get_owned_conversation
from app.services.history_trim import trim_history

log = logging.getLogger("app.services.history")

CACHE_TTL_SECONDS = 3600
TITLE_MAX_CHARS = 60


def derive_title(text: str) -> str:
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= TITLE_MAX_CHARS else one_line[: TITLE_MAX_CHARS - 1].rstrip() + "…"


def _cache_key(conversation_id: str) -> str:
    return f"chat:history:{conversation_id}"


class HistoryService:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        redis,
        *,
        max_turns: int,
        max_tokens: int,
        count_tokens: Callable[[str], int] = estimate_tokens,
    ):
        self._uow = uow_factory
        self._redis = redis
        self.max_messages = max_turns * 2          # 1 lượt = 1 câu hỏi + 1 câu trả lời
        self.max_tokens = max_tokens
        self._count_tokens = count_tokens

    # ---------------- cache (best effort) ----------------
    async def _cache_read(self, conversation_id: str) -> list[dict] | None:
        if self._redis is None:
            return None
        try:
            raw = await self._redis.lrange(_cache_key(conversation_id), 0, -1)
            return [json.loads(x) for x in raw] if raw else None
        except Exception:  # noqa: BLE001
            log.warning("Đọc cache lịch sử lỗi, dùng MySQL", exc_info=True)
            return None

    async def _cache_replace(self, conversation_id: str, messages: list[dict]) -> None:
        if self._redis is None or not messages:
            return
        key = _cache_key(conversation_id)
        try:
            pipe = self._redis.pipeline(transaction=True)
            pipe.delete(key)
            pipe.rpush(key, *[json.dumps(m, ensure_ascii=False) for m in messages])
            pipe.expire(key, CACHE_TTL_SECONDS)
            await pipe.execute()
        except Exception:  # noqa: BLE001
            log.warning("Ghi cache lịch sử lỗi", exc_info=True)

    async def _cache_append(self, conversation_id: str, messages: list[dict]) -> None:
        if self._redis is None:
            return
        key = _cache_key(conversation_id)
        try:
            if not await self._redis.exists(key):
                return                                    # cache nguội: lần đọc sau nạp lại từ MySQL
            pipe = self._redis.pipeline(transaction=True)
            pipe.rpush(key, *[json.dumps(m, ensure_ascii=False) for m in messages])
            pipe.ltrim(key, -self.max_messages, -1)
            pipe.expire(key, CACHE_TTL_SECONDS)
            await pipe.execute()
        except Exception:  # noqa: BLE001
            log.warning("Cập nhật cache lịch sử lỗi, xóa cache để tránh lệch", exc_info=True)
            await self._cache_drop(conversation_id)

    async def _cache_drop(self, conversation_id: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.delete(_cache_key(conversation_id))
        except Exception:  # noqa: BLE001
            log.warning("Xóa cache lịch sử lỗi", exc_info=True)

    # ---------------- API ----------------
    async def recent(self, conversation_id: str) -> list[dict]:
        """Các lượt gần nhất (cũ -> mới) đã cắt theo HISTORY_MAX_TURNS/HISTORY_MAX_TOKENS."""
        messages = await self._cache_read(conversation_id)
        if messages is None:
            async with self._uow() as uow:
                rows = await uow.messages.list_recent(conversation_id, self.max_messages)
                messages = [{"role": m.role, "content": m.content} for m in rows]
            await self._cache_replace(conversation_id, messages)
        return trim_history(
            messages,
            max_messages=self.max_messages,
            max_tokens=self.max_tokens,
            count_tokens=self._count_tokens,
        )

    async def save_turn(
        self,
        conversation_id: str,
        user_text: str,
        result,
        *,
        request_id: str | None = None,
        user_at: datetime | None = None,
    ) -> str:
        """Lưu cặp message, trả `message_id` của câu trả lời. Lưu cả sources và trace.

        `user_at` = thời điểm nhận câu hỏi; câu trả lời luôn có created_at SAU câu hỏi để thứ tự ổn định.
        """
        user_at = user_at or utcnow()
        assistant_at = max(utcnow(), user_at + timedelta(microseconds=1))
        user_msg = ChatMessage(
            id=new_id("m"), conversation_id=conversation_id, role=Role.USER.value,
            content=user_text, request_id=request_id, created_at=user_at,
        )
        assistant_msg = ChatMessage(
            id=new_id("m"), conversation_id=conversation_id, role=Role.ASSISTANT.value,
            content=result.answer, intent=result.intent.value,
            sources=[s.model_dump(by_alias=True, mode="json") for s in result.sources],
            trace={**trace_to_dict(result.trace), "fallback_reason": result.fallback_reason},
            request_id=request_id, created_at=assistant_at,
        )
        async with self._uow() as uow:
            await uow.messages.add_many([user_msg, assistant_msg])
            await uow.conversations.touch(conversation_id, title=derive_title(user_text))
        await self._cache_append(conversation_id, [
            {"role": user_msg.role, "content": user_msg.content},
            {"role": assistant_msg.role, "content": assistant_msg.content},
        ])
        return assistant_msg.id

    async def get_history(
        self, *, user_id: str | None, conversation_id: str, page: int, page_size: int
    ) -> ConversationHistoryResponse:
        async with self._uow() as uow:
            await get_owned_conversation(uow.conversations, user_id, conversation_id)
            rows, total = await uow.messages.list_page(
                conversation_id, offset=(page - 1) * page_size, limit=page_size
            )
            items = [_to_message_item(m) for m in rows]
        return ConversationHistoryResponse(
            conversation_id=conversation_id, messages=items, page=page, page_size=page_size, total=total
        )

    async def delete_history(self, *, user_id: str | None, conversation_id: str) -> None:
        async with self._uow() as uow:
            await get_owned_conversation(uow.conversations, user_id, conversation_id)
            await uow.conversations.soft_delete(conversation_id)
        await self._cache_drop(conversation_id)


def _to_message_item(m: ChatMessage) -> MessageItem:
    try:
        intent = Intent(m.intent) if m.intent else None
    except ValueError:
        intent = None
    sources = []
    for raw in m.sources or []:
        try:
            sources.append(SourceItem.model_validate(raw))
        except ValueError:       # dữ liệu cũ sai định dạng không được làm hỏng cả lịch sử
            log.warning("Bỏ qua source không hợp lệ ở message %s", m.id)
    return MessageItem(
        message_id=m.id, role=Role(m.role), content=m.content, intent=intent,
        sources=sources, created_at=m.created_at,
    )
