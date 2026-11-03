"""Kiểm tra các hợp đồng cốt lõi (chạy được ngay, không cần hạ tầng)."""
from app.ingestion.payload import ChunkPayload, ContentType, content_hash, point_id
from app.schemas.chat_schema import ChatResponse, Intent


def test_point_id_is_stable_and_unique():
    a = point_id(ContentType.FAQ, "faq-order-001", 0)
    assert a == point_id(ContentType.FAQ, "faq-order-001", 0)
    assert a != point_id(ContentType.FAQ, "faq-order-001", 1)
    assert a != point_id(ContentType.POLICY, "faq-order-001", 0)


def test_payload_omits_none_fields():
    p = ChunkPayload(chunk_id="c", document_id="d", content_type="FAQ", title="t", text="x",
                     chunk_index=0, content_hash=content_hash("x"), updated_at="2026-01-01T00:00:00Z")
    d = p.to_dict()
    assert "price_snapshot" not in d and d["enabled"] is True


def test_chat_response_requires_message_id_and_uses_camel_case():
    r = ChatResponse(conversation_id="c1", message_id="m1", answer="ok", intent=Intent.FAQ_POLICY)
    dumped = r.model_dump(by_alias=True)
    assert dumped["messageId"] == "m1" and dumped["conversationId"] == "c1"
