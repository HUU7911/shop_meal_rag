"""Dựng RAGEngine từ Settings. Gọi một lần trong lifespan (main.py) khi RAG_ENABLED=true.

Nạp model là việc nặng (có thể tải vài GB lần đầu) -> chạy trong thread, không chặn event loop.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable

from qdrant_client import AsyncQdrantClient

from app.core.errors import ConfigurationError
from app.embedding.embedding_service import EmbeddingService
from app.rag.context_builder import ContextBuilder
from app.rag.guardrails import Guardrails
from app.rag.intent_router import IntentRouter
from app.rag.llm_service import LLMService
from app.rag.prompt_builder import PromptBuilder
from app.rag.query_processor import QueryProcessor
from app.rag.rag_engine import DefaultRAGEngine
from app.rag.reranker import Reranker
from app.rag.retriever import Retriever

log = logging.getLogger("app.rag.factory")


async def build_retrieval_stack(settings):
    """(client, embedder, retriever, reranker) – dùng chung cho engine và script eval/seed."""
    api_key = settings.qdrant_api_key.get_secret_value() or None
    client = AsyncQdrantClient(url=settings.qdrant_url, api_key=api_key)
    embedder = await asyncio.to_thread(EmbeddingService, settings.embedding_model, settings.embedding_dim,
                                       settings.embedding_device)
    reranker = await asyncio.to_thread(Reranker, settings.rerank_model, enabled=settings.rerank_enabled,
                                       device=settings.embedding_device)
    retriever = Retriever(client, embedder, collection=settings.qdrant_collection,
                          hybrid_enabled=settings.hybrid_enabled, top_k=settings.retrieval_top_k)
    return client, embedder, retriever, reranker


async def build_rag_engine(settings, product_client, order_client
                           ) -> tuple[DefaultRAGEngine, Callable[[], Awaitable[None]]]:
    if not settings.llm_model:
        raise ConfigurationError("RAG_ENABLED=true nhưng LLM_MODEL chưa cấu hình")
    client, embedder, retriever, reranker = await build_retrieval_stack(settings)
    await retriever.verify()                       # lệch dim/model -> dừng khởi động với lỗi rõ ràng
    llm = LLMService(settings)
    engine = DefaultRAGEngine(
        settings=settings, retriever=retriever, reranker=reranker,
        query_processor=QueryProcessor(llm), router=IntentRouter(),
        guardrails=Guardrails(max_length=settings.message_max_length, support_contact=settings.support_contact),
        context_builder=ContextBuilder(), prompt_builder=PromptBuilder(), llm=llm,
        product_client=product_client, order_client=order_client)

    async def close() -> None:
        await llm.aclose()
        await client.close()

    log.info("RAGEngine sẵn sàng (embedding=%s, rerank=%s, hybrid=%s, prompt=%s)", embedder.model_name,
             settings.rerank_enabled, settings.hybrid_enabled and embedder.supports_sparse,
             engine.prompt_builder.version)
    return engine, close