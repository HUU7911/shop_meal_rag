"""HỢP ĐỒNG RAG (Member 02 ⇄ Member 01). Xem docs/CONTRACTS.md.

Module rag KHÔNG đọc/ghi MySQL và không biết HTTP. Nhận RAGRequest, trả RAGResult.
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.schemas.chat_schema import Intent, SourceItem, SourceType

# Giá trị hợp lệ của RAGResult.fallback_reason
FALLBACK_REASONS = (
    "NO_CONTEXT",        # không tìm thấy thông tin liên quan
    "LLM_UNAVAILABLE",   # LLM lỗi/timeout sau retry + dự phòng
    "UPSTREAM_DOWN",     # Qdrant/Product/Order Service không dùng được
    "BLOCKED",           # guardrail đầu vào chặn
    "LOGIN_REQUIRED",    # cần đăng nhập (tra đơn hàng)
    "OUT_OF_SCOPE",      # ngoài phạm vi Shop Meal
    "UNSAFE_OUTPUT",     # guardrail đầu ra thay câu trả lời
)


@dataclass(frozen=True)
class RAGUser:
    user_id: str | None
    roles: tuple[str, ...] = ()
    token: str | None = None            # chuyển tiếp cho Order Service (chỉ ORDER_STATUS)

    @property
    def is_guest(self) -> bool:
        return self.user_id is None


@dataclass(frozen=True)
class HistoryTurn:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class RAGRequest:
    question: str
    history: list[HistoryTurn]          # đã cắt theo token budget bởi ChatService
    user: RAGUser
    request_id: str


@dataclass
class Hit:
    """Một chunk truy xuất được từ Qdrant."""
    chunk_id: str
    document_id: str
    content_type: str                   # FAQ | POLICY | PRODUCT | DOCUMENT
    title: str
    text: str
    score: float
    score_kind: str = "cosine"          # "cosine" (dense) | "rrf" (hybrid, không so với ngưỡng cosine)
    rerank_score: float | None = None
    payload: dict = field(default_factory=dict)

    @property
    def product_id(self) -> str:
        return str(self.payload.get("product_id") or self.document_id)


@dataclass
class ToolResult:
    """Kết quả của một tool (dữ liệu LIVE). `text` là phần đưa vào context cho LLM."""
    tool: str
    kind: SourceType
    ref_id: str
    title: str
    text: str
    url: str | None = None
    ok: bool = True                     # False = dịch vụ ngoài lỗi (text là ghi chú "không kiểm tra được")
    found: bool = True                  # False = không có dữ liệu (không tạo SourceItem)


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    score: float
    rerank_score: float | None = None


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass
class RAGTrace:
    """Lưu cùng message để truy ngược khi có feedback."""
    standalone_question: str | None = None
    filters: dict = field(default_factory=dict)
    retrieved: list[RetrievedChunk] = field(default_factory=list)
    tools_called: list[str] = field(default_factory=list)
    model: str | None = None
    prompt_version: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)
    # rewrite / route / retrieve (gồm embed) / rerank / tools / llm / total  (ms)
    latency_ms: dict[str, int] = field(default_factory=dict)


@dataclass
class RAGResult:
    answer: str
    intent: Intent
    sources: list[SourceItem] = field(default_factory=list)
    trace: RAGTrace = field(default_factory=RAGTrace)
    fallback_reason: str | None = None  # một trong FALLBACK_REASONS


@dataclass
class RAGEvent:
    """Sự kiện stream. `done` mang RAGResult cuối cùng — client nên ưu tiên `done.answer`
    (guardrail đầu ra có thể thay câu trả lời sau khi token đã phát)."""
    type: Literal["token", "sources", "done", "error"]
    data: str | list[SourceItem] | RAGResult | None = None


class RAGEngine(Protocol):
    async def invoke(self, request: RAGRequest) -> RAGResult: ...
    def stream(self, request: RAGRequest) -> AsyncIterator[RAGEvent]: ...
