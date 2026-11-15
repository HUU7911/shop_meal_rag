"""Ánh xạ RAGResult -> ChatResponse / bản ghi lưu DB. Member 01 (ChatService) chỉ cần gọi hai hàm này.

Quy ước (docs/CONTRACTS.md §2):
  * fallback_reason của RAG -> ChatMetadata.fallback
  * trace -> chat_messages.trace (JSON) để truy ngược khi có feedback
  * sources lưu nguyên dạng JSON (camelCase, giống API) để GET /history trả lại đúng dạng
"""
import dataclasses

from app.rag.types import RAGResult, RAGTrace
from app.schemas.chat_schema import ChatMetadata, ChatResponse


def to_chat_response(result: RAGResult, *, conversation_id: str, message_id: str) -> ChatResponse:
    return ChatResponse(
        conversation_id=conversation_id, message_id=message_id, answer=result.answer, intent=result.intent,
        sources=result.sources,
        metadata=ChatMetadata(model=result.trace.model, prompt_version=result.trace.prompt_version,
                              retrieval_count=len(result.trace.retrieved), fallback=result.fallback_reason))


def trace_to_dict(trace: RAGTrace) -> dict:
    """Dict thuần JSON (lưu vào cột JSON). Gồm cả `dropped` (chunk bị ngưỡng loại) để debug."""
    return dataclasses.asdict(trace)