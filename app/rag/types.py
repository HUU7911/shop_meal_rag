"""HỢP ĐỒNG RAG (Member 02 ⇄ Member 01). Xem docs/CONTRACTS.md.

Module rag KHÔNG đọc/ghi MySQL và không biết HTTP. Nhận RAGRequest, trả RAGResult.
"""
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol

from app.schemas.chat_schema import Intent, SourceItem


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
class RetrievedChunk:
    chunk_id: str
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
    latency_ms: dict[str, int] = field(default_factory=dict)   # rewrite/route/embed/retrieve/rerank/llm/total


@dataclass
class RAGResult:
    answer: str
    intent: Intent
    sources: list[SourceItem] = field(default_factory=list)
    trace: RAGTrace = field(default_factory=RAGTrace)
    fallback_reason: str | None = None  # NO_CONTEXT | LLM_UNAVAILABLE | UPSTREAM_DOWN | BLOCKED | LOGIN_REQUIRED


@dataclass
class RAGEvent:
    type: Literal["token", "sources", "done", "error"]
    data: str | list[SourceItem] | RAGResult | None = None


class RAGEngine(Protocol):
    async def invoke(self, request: RAGRequest) -> RAGResult: ...
    def stream(self, request: RAGRequest) -> AsyncIterator[RAGEvent]: ...
