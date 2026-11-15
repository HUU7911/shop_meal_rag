"""Bản giả để test RAGEngine mà không cần Qdrant/LLM/Product/Order Service."""
from types import SimpleNamespace

from app.core.errors import GenerationError
from app.integrations.order_client import OrderInfo
from app.integrations.product_client import ProductInfo
from app.rag.protocols import LLMChunk
from app.rag.types import Hit


def make_settings(**over):
    base = dict(retrieval_top_k=8, rerank_top_n=4, retrieval_score_threshold=0.35, context_max_tokens=1800,
                llm_max_output_tokens=300, support_contact="CSKH Shop Meal")
    base.update(over)
    return SimpleNamespace(**base)


def faq_hit(doc="cancellation", text="Khách có thể hủy đơn khi chưa xác nhận.", score=0.8, kind="cosine", **kw):
    return Hit(chunk_id=f"{doc}-0", document_id=doc, content_type=kw.pop("content_type", "POLICY"),
               title="Chính sách hủy đơn", text=text, score=score, score_kind=kind, payload=kw)


def product_hit(pid="product-001", score=0.8):
    return Hit(chunk_id=f"{pid}-0", document_id=pid, content_type="PRODUCT", title="Cơm gà xối mỡ",
               text="Cơm gà giòn, ăn kèm dưa leo.", score=score, payload={"product_id": pid})


class FakeRetriever:
    def __init__(self, hits=None, error=None):
        self.hits, self.error, self.calls = hits or [], error, []

    async def search(self, question, *, content_types=None, filters=None, top_k=None):
        self.calls.append({"q": question, "types": content_types, "filters": filters})
        if self.error:
            raise self.error
        return list(self.hits)


class FakeReranker:
    enabled = False

    def rerank(self, question, hits, top_n):
        return hits[:top_n]


class FakeLLM:
    model_name = "fake-llm"

    def __init__(self, answer="Câu trả lời thử.", fail=False, tokens=("Xin ", "chào")):
        self.answer, self.fail, self.tokens, self.last_messages, self.calls = answer, fail, tokens, None, 0

    async def generate(self, messages, *, max_tokens=None, temperature=0.2):
        self.calls += 1
        self.last_messages = messages
        if self.fail:
            raise GenerationError("boom")
        return self.answer, {"prompt_tokens": 10, "completion_tokens": 5}

    async def stream(self, messages, *, max_tokens=None, temperature=0.2):
        self.last_messages = messages
        if self.fail:
            raise GenerationError("boom")
        for t in self.tokens:
            yield LLMChunk(text=t)
        yield LLMChunk(usage={"prompt_tokens": 10, "completion_tokens": 2})


class FakeProductClient:
    def __init__(self, items=None, down=False):
        self.items = {i.product_id: i for i in (items or [])}
        self.down, self.search_calls = down, []

    async def get(self, product_id):
        if self.down:
            raise RuntimeError("down")
        return self.items.get(product_id)

    async def search(self, **kw):
        self.search_calls.append(kw)
        if self.down:
            raise RuntimeError("down")
        return list(self.items.values()), len(self.items)


class FakeOrderClient:
    def __init__(self, orders=None):
        self.orders, self.tokens_seen = {o.order_id: o for o in (orders or [])}, []

    async def get_order(self, order_id, *, user_token):
        self.tokens_seen.append(user_token)
        return self.orders.get(order_id)

    async def list_recent(self, *, user_token, limit=5):
        self.tokens_seen.append(user_token)
        return list(self.orders.values())[:limit]


def product(pid="product-001", name="Cơm gà xối mỡ", price=45000, status="AVAILABLE"):
    return ProductInfo(product_id=pid, name=name, description="Cơm gà giòn", category="RICE",
                       product_type="MAIN", price=price, status=status, url=f"/products/{pid}")


def order(oid="123", status="DELIVERING"):
    return OrderInfo(order_id=oid, status=status, total=90000, created_at="2026-11-05 10:00",
                     items=[{"name": "Cơm gà", "quantity": 2}])
