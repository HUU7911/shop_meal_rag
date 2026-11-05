"""Điều phối pipeline RAG. Triển khai `RAGEngine` (xem rag/types.py).

guardrails(in) -> query_processor -> intent_router
    FAQ_POLICY     -> retriever -> rerank -> ngưỡng điểm
    PRODUCT_*      -> retriever(PRODUCT) -> tool product_* (giá/trạng thái LIVE)
    ORDER_STATUS   -> tool order_status (cần đăng nhập)
    SMALLTALK / OUT_OF_SCOPE -> trả lời có sẵn, KHÔNG gọi LLM
-> context_builder -> (không có context -> fallback, KHÔNG gọi LLM)
-> prompt_builder -> llm -> guardrails(out) -> RAGResult

Mọi thay đổi chất lượng phải kèm kết quả `make eval`.
"""
import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.core.errors import EmbeddingError, GenerationError, GuardrailBlocked, RetrievalError, VectorDatabaseError
from app.rag import messages as msg
from app.rag.context_builder import BuiltContext
from app.rag.tools.order_status import order_status
from app.rag.tools.product_detail import product_detail
from app.rag.tools.product_search import product_search
from app.rag.types import (Hit, RAGEvent, RAGRequest, RAGResult, RAGTrace, RetrievedChunk, TokenUsage,
                           ToolResult)
from app.rag.utils import timed
from app.schemas.chat_schema import Intent, SourceItem

log = logging.getLogger("app.rag.engine")
_RETRIEVAL_ERRORS = (EmbeddingError, VectorDatabaseError, RetrievalError)
KNOWLEDGE_TYPES = ["FAQ", "POLICY", "DOCUMENT"]


@dataclass
class _Prepared:
    """Kết quả bước chuẩn bị: hoặc đã có `result` (không cần LLM) hoặc có `messages` để gọi LLM."""
    trace: RAGTrace
    intent: Intent
    started: float
    result: RAGResult | None = None
    messages: list[dict] = field(default_factory=list)
    built: BuiltContext = field(default_factory=BuiltContext)
    question: str = ""


class DefaultRAGEngine:
    def __init__(self, *, settings, retriever, reranker, query_processor, router, guardrails,
                 context_builder, prompt_builder, llm, product_client, order_client):
        self.s = settings
        self.retriever, self.reranker, self.qp, self.router = retriever, reranker, query_processor, router
        self.guardrails, self.context_builder, self.prompt_builder = guardrails, context_builder, prompt_builder
        self.llm, self.product_client, self.order_client = llm, product_client, order_client

    # ================= API =================
    async def invoke(self, request: RAGRequest) -> RAGResult:
        prep = await self._prepare(request)
        if prep.result is not None:
            return prep.result
        try:
            with timed(prep.trace, "llm"):
                answer, usage = await self.llm.generate(prep.messages, max_tokens=self.s.llm_max_output_tokens)
        except GenerationError:
            log.warning("LLM lỗi", exc_info=True)
            return self._done(prep, msg.llm_unavailable(self.s.support_contact), "LLM_UNAVAILABLE")
        return self._finalize(prep, answer, usage)

    async def stream(self, request: RAGRequest) -> AsyncIterator[RAGEvent]:
        prep = await self._prepare(request)
        if prep.result is not None:
            yield RAGEvent("token", prep.result.answer)
            yield RAGEvent("sources", prep.result.sources)
            yield RAGEvent("done", prep.result)
            return
        parts: list[str] = []
        usage: dict = {}
        started = time.perf_counter()
        try:
            async for chunk in self.llm.stream(prep.messages, max_tokens=self.s.llm_max_output_tokens):
                if chunk.text:
                    parts.append(chunk.text)
                    yield RAGEvent("token", chunk.text)
                if chunk.usage:
                    usage = chunk.usage
        except GenerationError:
            log.warning("LLM stream lỗi", exc_info=True)
            if parts:                                   # đã phát một phần: báo lỗi, không thể rút lại
                yield RAGEvent("error", msg.llm_unavailable(self.s.support_contact))
                return
            result = self._done(prep, msg.llm_unavailable(self.s.support_contact), "LLM_UNAVAILABLE")
            yield RAGEvent("token", result.answer)
            yield RAGEvent("sources", result.sources)
            yield RAGEvent("done", result)
            return
        prep.trace.latency_ms["llm"] = int((time.perf_counter() - started) * 1000)
        final = self._finalize(prep, "".join(parts), usage)
        yield RAGEvent("sources", final.sources)
        yield RAGEvent("done", final)             # client ưu tiên final.answer (guardrail có thể đã thay)

    # ================= chuẩn bị (dùng chung cho invoke/stream) =================
    async def _prepare(self, request: RAGRequest) -> _Prepared:
        trace = RAGTrace(model=getattr(self.llm, "model_name", None),
                         prompt_version=self.prompt_builder.version)
        prep = _Prepared(trace=trace, intent=Intent.FAQ_POLICY, started=time.perf_counter(),
                         question=request.question)
        contact = self.s.support_contact

        try:
            question = self.guardrails.check_input(request.question)
        except GuardrailBlocked:
            prep.intent = Intent.OUT_OF_SCOPE
            prep.result = self._done(prep, msg.BLOCKED, "BLOCKED")
            return prep
        prep.question = question

        with timed(trace, "rewrite"):
            pq = await self.qp.process(question, request.history)
        trace.standalone_question, trace.filters = pq.standalone, pq.filters

        with timed(trace, "route"):
            intent = self.router.route(pq.standalone, pq.filters)
        prep.intent = intent

        if intent is Intent.SMALLTALK:
            prep.result = self._done(prep, msg.smalltalk(question), None)
            return prep
        if intent is Intent.OUT_OF_SCOPE:
            prep.result = self._done(prep, msg.OUT_OF_SCOPE, "OUT_OF_SCOPE")
            return prep
        if intent is Intent.ORDER_STATUS and (request.user.is_guest or not request.user.token):
            prep.result = self._done(prep, msg.LOGIN_REQUIRED, "LOGIN_REQUIRED")
            return prep

        hits: list[Hit] = []
        tool_results: list[ToolResult] = []
        retrieval_failed = False

        if intent is Intent.FAQ_POLICY:
            hits, retrieval_failed = await self._retrieve(pq, KNOWLEDGE_TYPES, trace)
        elif intent in (Intent.PRODUCT_SEARCH, Intent.PRODUCT_DETAIL):
            hits, retrieval_failed = await self._retrieve(pq, ["PRODUCT"], trace)
            tool_results = await self._product_tools(intent, hits, pq.filters, trace)
            live_ids = {t.ref_id for t in tool_results if t.ok and t.found}
            hits = [h for h in hits if h.product_id in live_ids]     # mô tả chỉ cho sản phẩm còn xác minh được
        elif intent is Intent.ORDER_STATUS:
            with timed(trace, "tools"):
                trace.tools_called.append("order_status")
                tool_results = await order_status(self.order_client, pq.filters.get("order_id"),
                                                  user_token=request.user.token)

        built = self.context_builder.build(hits, tool_results, self.s.context_max_tokens)
        prep.built = built
        if not built.has_context:
            tools_down = tool_results and all(not t.ok for t in tool_results)
            if retrieval_failed or tools_down:
                prep.result = self._done(prep, msg.upstream_down(contact), "UPSTREAM_DOWN")
            elif tool_results:          # tool chạy ổn nhưng không có dữ liệu (vd. không thấy đơn): nói thẳng
                prep.result = self._done(prep, tool_results[0].text, "NO_CONTEXT")
            else:
                prep.result = self._done(prep, msg.no_info(contact), "NO_CONTEXT")
            return prep

        prep.messages = self.prompt_builder.build(question=question, standalone=pq.standalone,
                                                  history=request.history, context=built.text, intent=intent)
        return prep

    # ================= các bước con =================
    async def _retrieve(self, pq, content_types: list[str], trace: RAGTrace) -> tuple[list[Hit], bool]:
        try:
            with timed(trace, "retrieve"):          # gồm cả thời gian embed câu hỏi
                hits = await self.retriever.search(pq.standalone, content_types=content_types,
                                                   filters=pq.filters, top_k=self.s.retrieval_top_k)
        except _RETRIEVAL_ERRORS:
            log.warning("Truy xuất lỗi", exc_info=True)
            return [], True
        if hits and self.reranker.enabled:
            with timed(trace, "rerank"):
                hits = await asyncio.to_thread(self.reranker.rerank, pq.standalone, hits, self.s.rerank_top_n)
        else:
            hits = hits[: self.s.rerank_top_n]
        hits = self._apply_threshold(hits)
        trace.retrieved.extend(RetrievedChunk(h.chunk_id, h.document_id, h.score, h.rerank_score) for h in hits)
        return hits, False

    def _apply_threshold(self, hits: list[Hit]) -> list[Hit]:
        """Ngưỡng theo loại điểm: rerank_score, hoặc cosine. Điểm RRF không có ý nghĩa tuyệt đối -> giữ nguyên.
        Ngưỡng PHẢI được hiệu chỉnh bằng `make eval` (RETRIEVAL_SCORE_THRESHOLD)."""
        t = self.s.retrieval_score_threshold
        kept = []
        for h in hits:
            if h.rerank_score is not None:
                if h.rerank_score >= t:
                    kept.append(h)
            elif h.score_kind == "cosine":
                if h.score >= t:
                    kept.append(h)
            else:
                kept.append(h)
        return kept

    async def _product_tools(self, intent: Intent, hits: list[Hit], filters: dict, trace: RAGTrace
                             ) -> list[ToolResult]:
        ids = list(dict.fromkeys(h.product_id for h in hits))
        with timed(trace, "tools"):
            if intent is Intent.PRODUCT_DETAIL:
                if not ids:                      # không xác định được món nào -> NO_CONTEXT, không liệt kê bừa
                    return []
                trace.tools_called.append("product_detail")
                return [await product_detail(self.product_client, ids[0])]
            trace.tools_called.append("product_search")
            return await product_search(self.product_client, product_ids=ids, filters=filters, size=5)

    # ================= kết quả =================
    def _done(self, prep: _Prepared, answer: str, fallback: str | None) -> RAGResult:
        prep.trace.latency_ms["total"] = int((time.perf_counter() - prep.started) * 1000)
        return RAGResult(answer=answer, intent=prep.intent, sources=prep.built.sources if fallback is None
                         and prep.built.has_context else [], trace=prep.trace, fallback_reason=fallback)

    def _finalize(self, prep: _Prepared, answer: str, usage: dict) -> RAGResult:
        prep.trace.usage = TokenUsage(usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
        checked = self.guardrails.check_output(answer, context_text=prep.built.text, question=prep.question)
        prep.trace.latency_ms["total"] = int((time.perf_counter() - prep.started) * 1000)
        sources: list[SourceItem] = [] if checked.fallback_reason else prep.built.sources
        return RAGResult(answer=checked.answer, intent=prep.intent, sources=sources, trace=prep.trace,
                         fallback_reason=checked.fallback_reason)
