import json

from app.rag.types import RAGResult, RAGTrace, RetrievedChunk, TokenUsage
from app.schemas.chat_schema import Intent, SourceItem, SourceType
from app.services.chat_mapper import to_chat_response, trace_to_dict


def make_result(fallback=None):
    trace = RAGTrace(standalone_question="q", filters={"max_price": 49999},
                     retrieved=[RetrievedChunk("c1", "faq-order-001", 1.0, 0.9)],
                     dropped=[RetrievedChunk("c2", "cancellation", 0.4, 0.0)], tools_called=["product_search"],
                     model="template-extractive", prompt_version="extractive-v1", usage=TokenUsage(0, 0),
                     latency_ms={"total": 12})
    src = SourceItem(type=SourceType.FAQ, id="faq-order-001", title="Đặt hàng")
    return RAGResult(answer="ok", intent=Intent.FAQ_POLICY, sources=[src], trace=trace, fallback_reason=fallback)


def test_to_chat_response_carries_ids_sources_and_metadata():
    resp = to_chat_response(make_result("NO_CONTEXT"), conversation_id="c_1", message_id="m_1")
    assert resp.conversation_id == "c_1" and resp.message_id == "m_1" and resp.answer == "ok"
    assert resp.intent is Intent.FAQ_POLICY and [s.id for s in resp.sources] == ["faq-order-001"]
    assert resp.metadata.fallback == "NO_CONTEXT" and resp.metadata.retrieval_count == 1
    assert resp.metadata.model == "template-extractive" and resp.metadata.prompt_version == "extractive-v1"


def test_trace_is_json_serializable_and_keeps_dropped_chunks():
    data = trace_to_dict(make_result().trace)
    json.dumps(data, ensure_ascii=False)                         # phải lưu được vào cột JSON
    assert data["retrieved"][0]["document_id"] == "faq-order-001"
    assert data["dropped"][0]["document_id"] == "cancellation" and data["latency_ms"]["total"] == 12