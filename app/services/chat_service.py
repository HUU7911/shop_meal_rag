"""Điều phối một lượt chat. Đây là service DUY NHẤT mà router chat gọi.

Trình tự:
 1. ConversationService: lấy/tạo conversation (kiểm tra chủ sở hữu)
 2. HistoryService: lấy lịch sử gần nhất theo HISTORY_MAX_TURNS / HISTORY_MAX_TOKENS
 3. RAGEngine.invoke(RAGRequest)  -> RAGResult      (KHÔNG giữ transaction DB trong lúc chờ RAG/LLM)
 4. HistoryService: lưu message user + assistant (kèm sources, trace)
 5. Trả ChatResponse (có message_id)

Quy tắc: ChatService không chứa logic embedding/chunking/truy vấn Qdrant.

Luồng stream: bước 1-2 chạy TRƯỚC khi trả StreamingResponse (lỗi 403/404 vẫn là HTTP status đúng).
Lượt chat lỗi giữa chừng hoặc client ngắt kết nối thì KHÔNG được lưu.
"""
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass
from datetime import datetime

from app.core.errors import AppError
from app.core.logging import request_id_ctx
from app.core.security import CurrentUser
from app.db.types import utcnow
from app.rag import messages as rag_messages
from app.rag.types import HistoryTurn, RAGRequest, RAGResult, RAGUser
from app.schemas.chat_schema import ChatRequest, ChatResponse, Intent
from app.services.chat_mapper import to_chat_response

log = logging.getLogger("app.services.chat")


@dataclass
class ChatStreamEvent:
    """Một sự kiện SSE: `event` in token|sources|done|error; `data` là dict sẽ được mã hóa JSON."""
    event: str
    data: dict


@dataclass
class _Turn:
    conversation_id: str
    question: str
    user: CurrentUser
    request_id: str
    received_at: datetime
    rag_request: RAGRequest


class ChatService:
    def __init__(self, *, conversations, history, rag_engine):
        self.conversations = conversations
        self.history = history
        self.rag = rag_engine

    # ---------------- public ----------------
    async def handle(self, user: CurrentUser, request: ChatRequest) -> ChatResponse:
        turn = await self._prepare(user, request)
        result = await self.rag.invoke(turn.rag_request)
        return await self._complete(turn, result)

    async def stream(self, user: CurrentUser, request: ChatRequest) -> AsyncIterator[ChatStreamEvent]:
        """Chuẩn bị (có thể raise AppError) rồi trả async iterator các sự kiện SSE."""
        turn = await self._prepare(user, request)
        return self._stream(turn)

    # ---------------- internals ----------------
    async def _prepare(self, user: CurrentUser, request: ChatRequest) -> _Turn:
        received_at = utcnow()
        conversation = await self.conversations.get_or_create(user.user_id, request.conversation_id)
        history = await self.history.recent(conversation.id)
        request_id = request_id_ctx.get()
        rag_request = RAGRequest(
            question=request.message,
            history=[HistoryTurn(role=h["role"], content=h["content"]) for h in history],
            user=RAGUser(user_id=user.user_id, roles=user.roles, token=user.token),
            request_id=request_id,
        )
        return _Turn(conversation.id, request.message, user, request_id, received_at, rag_request)

    def _enforce_guest_policy(self, turn: _Turn, result: RAGResult) -> RAGResult:
        """Phòng thủ nhiều lớp: khách KHÔNG BAO GIỜ nhận dữ liệu đơn hàng, kể cả khi RAG có lỗi."""
        if (turn.user.is_guest and result.intent is Intent.ORDER_STATUS
                and result.fallback_reason != "LOGIN_REQUIRED"):
            log.error("RAG trả dữ liệu ORDER_STATUS cho khách; đã thay bằng yêu cầu đăng nhập")
            return RAGResult(answer=rag_messages.LOGIN_REQUIRED, intent=result.intent, sources=[],
                             trace=result.trace, fallback_reason="LOGIN_REQUIRED")
        return result

    async def _complete(self, turn: _Turn, result: RAGResult) -> ChatResponse:
        result = self._enforce_guest_policy(turn, result)
        message_id = await self.history.save_turn(
            turn.conversation_id, turn.question, result,
            request_id=turn.request_id, user_at=turn.received_at,
        )
        return to_chat_response(result, conversation_id=turn.conversation_id, message_id=message_id)

    async def _stream(self, turn: _Turn) -> AsyncIterator[ChatStreamEvent]:
        final: RAGResult | None = None
        try:
            async with aclosing(self.rag.stream(turn.rag_request)) as events:
                async for event in events:
                    if event.type == "token":
                        yield ChatStreamEvent("token", {"text": event.data})
                    elif event.type == "sources":
                        if not (turn.user.is_guest and any(s.type.value == "ORDER" for s in event.data)):
                            yield ChatStreamEvent("sources", {"sources": [
                                s.model_dump(by_alias=True, mode="json") for s in event.data]})
                    elif event.type == "done":
                        final = event.data
                        break
                    elif event.type == "error":
                        yield self._error_event("GENERATION_ERROR", str(event.data), turn.request_id)
                        return
            if final is None:
                yield self._error_event("GENERATION_ERROR", "Luồng trả lời kết thúc bất thường.", turn.request_id)
                return
            response = await self._complete(turn, final)
            yield ChatStreamEvent("done", response.model_dump(by_alias=True, mode="json"))
        except AppError as exc:
            log.warning("Stream lỗi: %s", exc.code, exc_info=exc)
            yield self._error_event(exc.code, exc.message, turn.request_id)
        except Exception:  # noqa: BLE001 - không để lộ chi tiết nội bộ; CancelledError không bị bắt
            log.exception("Stream lỗi không mong đợi")
            yield self._error_event("INTERNAL_ERROR", "Đã xảy ra lỗi hệ thống.", turn.request_id)

    @staticmethod
    def _error_event(code: str, message: str, request_id: str) -> ChatStreamEvent:
        return ChatStreamEvent("error", {"code": code, "message": message, "requestId": request_id})
