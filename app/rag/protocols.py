"""Giao diện (duck-typing) của các thành phần RAG, để RAGEngine test được bằng bản giả."""
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol

from app.rag.types import Hit


@dataclass
class LLMChunk:
    text: str | None = None
    usage: dict | None = None            # {"prompt_tokens": int, "completion_tokens": int}


class RetrieverLike(Protocol):
    async def search(self, question: str, *, content_types: list[str] | None = None,
                     filters: dict | None = None, top_k: int | None = None) -> list[Hit]: ...


class RerankerLike(Protocol):
    enabled: bool
    def rerank(self, question: str, hits: list[Hit], top_n: int) -> list[Hit]: ...


class LLMLike(Protocol):
    model_name: str
    async def generate(self, messages: list[dict], *, max_tokens: int | None = None,
                       temperature: float = 0.2) -> tuple[str, dict]: ...
    def stream(self, messages: list[dict], *, max_tokens: int | None = None,
               temperature: float = 0.2) -> AsyncIterator[LLMChunk]: ...
