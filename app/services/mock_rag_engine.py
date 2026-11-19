"""MockRAGEngine (Mốc 0): trả RAGResult giả, KHÔNG cần Qdrant/LLM/model. Dùng khi RAG_ENABLED=false
và trong test API, để Member 01 và frontend làm việc song song với Member 02.

Hành vi tất định, đủ để thử các nhánh của API: chào hỏi, FAQ có `sources`, tìm sản phẩm,
đơn hàng (khách bị chặn bằng LOGIN_REQUIRED giống RAGEngine thật), ngoài phạm vi.
"""
from collections.abc import AsyncIterator

from app.rag import messages as msg
from app.rag.types import RAGEvent, RAGRequest, RAGResult, RAGTrace, RetrievedChunk
from app.rag.utils import strip_accents
from app.schemas.chat_schema import Intent, SourceItem, SourceType

MODEL = "mock-rag"
PROMPT_VERSION = "mock-v0"


class MockRAGEngine:
    def __init__(self, support_contact: str = "bộ phận chăm sóc khách hàng của Shop Meal"):
        self.contact = support_contact

    def _classify(self, question: str) -> Intent:
        q = strip_accents(question)
        if any(w in q for w in ("don hang", "ma don", "don #", "order")):
            return Intent.ORDER_STATUS
        if any(w in q for w in ("xin chao", "hello", "cam on")):
            return Intent.SMALLTALK
        if any(w in q for w in ("thoi tiet", "bong da", "chung khoan")):
            return Intent.OUT_OF_SCOPE
        if any(w in q for w in ("mon", "com", "gia", "con hang")):
            return Intent.PRODUCT_SEARCH
        return Intent.FAQ_POLICY

    async def invoke(self, request: RAGRequest) -> RAGResult:
        intent = self._classify(request.question)
        trace = RAGTrace(standalone_question=request.question, model=MODEL,
                         prompt_version=PROMPT_VERSION, latency_ms={"total": 1})
        if intent is Intent.ORDER_STATUS and (request.user.is_guest or not request.user.token):
            return RAGResult(msg.LOGIN_REQUIRED, intent, [], trace, "LOGIN_REQUIRED")
        if intent is Intent.OUT_OF_SCOPE:
            return RAGResult(msg.OUT_OF_SCOPE, intent, [], trace, "OUT_OF_SCOPE")
        if intent is Intent.SMALLTALK:
            return RAGResult(msg.smalltalk(request.question), intent, [], trace, None)
        if intent is Intent.ORDER_STATUS:
            return RAGResult("[MOCK] Đơn hàng của bạn đang được giao.", intent, [], trace, None)
        if intent is Intent.PRODUCT_SEARCH:
            source = SourceItem(type=SourceType.PRODUCT, id="product-001", title="Cơm gà xối mỡ",
                                snippet="Cơm gà giòn (dữ liệu giả).", url="/products/product-001", score=0.82)
            trace.retrieved = [RetrievedChunk("product-001-0", "product-001", 0.82)]
            return RAGResult("[MOCK] Có món Cơm gà xối mỡ phù hợp với bạn.", intent, [source], trace, None)
        source = SourceItem(type=SourceType.POLICY, id="cancellation_policy", title="Chính sách hủy đơn",
                            snippet="Khách có thể hủy đơn khi chưa xác nhận (dữ liệu giả).",
                            url="/policies/cancellation", score=0.9)
        trace.retrieved = [RetrievedChunk("cancellation_policy-0", "cancellation_policy", 0.9)]
        return RAGResult("[MOCK] Bạn có thể hủy đơn khi đơn chưa được xác nhận.", intent, [source], trace, None)

    async def stream(self, request: RAGRequest) -> AsyncIterator[RAGEvent]:
        result = await self.invoke(request)
        for word in result.answer.split(" "):
            yield RAGEvent("token", word + " ")
        yield RAGEvent("sources", result.sources)
        yield RAGEvent("done", result)
