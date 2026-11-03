"""Điều phối pipeline RAG. Triển khai `RAGEngine` (xem rag/types.py).

Trình tự: guardrails(in) -> query_processor -> intent_router
          -> [retriever -> reranker | tools] -> context_builder -> prompt_builder
          -> llm_service -> guardrails(out) -> RAGResult
Mỗi bước ghi thời gian vào trace.latency_ms.
"""
from app.rag.types import RAGRequest, RAGResult


class DefaultRAGEngine:
    async def invoke(self, request: RAGRequest) -> RAGResult:
        raise NotImplementedError  # TODO(Member 02)
