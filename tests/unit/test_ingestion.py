import asyncio
from app.ingestion.chunking import chunk_faq, chunk_policy, chunk_product
from app.ingestion.cleaner import clean_record
from app.ingestion.loaders.document_loader import DocumentLoader
from app.ingestion.loaders.faq_loader import FAQLoader
from app.ingestion.loaders.policy_loader import PolicyLoader
from app.ingestion.loaders.product_loader import ProductLoader
from app.ingestion.registry import IngestionRegistry
from app.integrations.product_client import ProductInfo


def test_faq_loader():
    loader = FAQLoader()
    records = loader.load()
    assert len(records) >= 30
    for r in records:
        assert "id" in r and "question" in r and "answer" in r


def test_policy_loader():
    loader = PolicyLoader()
    records = loader.load()
    assert len(records) >= 3
    ids = {r["policy_id"] for r in records}
    assert "cancellation" in ids
    assert "delivery" in ids
    assert "privacy" in ids


def test_document_loader(tmp_path=None):
    loader = DocumentLoader()
    records = loader.load()
    assert isinstance(records, list)


def test_product_loader():
    class FakeProductClient:
        def iter_all(self, page_size=100):
            yield ProductInfo(
                product_id="test-p1",
                name="Trà đào cam sả",
                description="Thanh mát",
                category="DRINK",
                product_type="DRINK",
                price=30000,
                status="AVAILABLE",
            )

    loader = ProductLoader(client=FakeProductClient())
    records = asyncio.run(loader.load_all())
    assert len(records) == 1
    assert records[0]["product_id"] == "test-p1"
    assert records[0]["price"] == 30000


def test_cleaner_valid_faq():
    raw = {
        "id": "faq-test-01",
        "question": "<b>Làm sao để đặt món?</b>",
        "answer": "Vào app và chọn món.",
        "keywords": ["đặt món", " "],
    }
    cleaned = clean_record(raw)
    assert cleaned is not None
    assert cleaned["question"] == "Làm sao để đặt món?"
    assert cleaned["keywords"] == ["đặt món"]


def test_cleaner_invalid_record():
    assert clean_record({}) is None
    assert clean_record("not a dict") is None
    assert clean_record({"unknown_field": 123}) is None


def test_chunk_faq():
    item = {
        "id": "faq-01",
        "question": "Có ship không?",
        "answer": "Có, phí 15k.",
        "keywords": ["ship", "giao hàng"],
        "category": "DELIVERY",
    }
    chunks = chunk_faq(item)
    assert len(chunks) == 1
    c = chunks[0]
    assert c.document_id == "faq-01"
    assert c.chunk_index == 0
    assert c.content_type == "FAQ"
    assert "ship" in c.embed_text
    assert c.enabled is True
    assert "embed_text" not in c.to_dict()  # verify to_dict excludes embed_text


def test_chunk_policy():
    markdown = """
## 1. Điều kiện hủy
Khách được hủy khi quán chưa làm.

## 2. Hoàn tiền
Hoàn tiền về thẻ trong 3 ngày.
"""
    meta = {"policy_id": "test_pol", "title": "Chính sách thử nghiệm", "version": "1.0"}
    chunks = chunk_policy(markdown, meta)
    assert len(chunks) == 2
    assert chunks[0].title == "Chính sách thử nghiệm"
    assert "Điều kiện hủy" in chunks[0].text
    assert "Hoàn tiền" in chunks[1].text
    assert chunks[0].chunk_index == 0
    assert chunks[1].chunk_index == 1


def test_chunk_product_no_price_in_embed_text():
    product = {
        "product_id": "prod-001",
        "name": "Cơm sườn bì chả",
        "category": "RICE",
        "description": "Sườn nướng thơm ngon",
        "price": 55000,
        "status": "AVAILABLE",
    }
    chunks = chunk_product(product)
    assert len(chunks) == 1
    c = chunks[0]
    # Qdrant payload snapshot has price, but text embed does NOT mention 55000
    assert "55000" not in c.text
    assert c.price_snapshot == 55000.0
    assert c.status_snapshot == "AVAILABLE"


def test_registry_fallback_without_db():
    registry = IngestionRegistry(session=None)
    plan = asyncio.run(registry.plan("FAQ", {"faq-1": "hash1", "faq-2": "hash2"}))
    assert plan["add"] == ["faq-1", "faq-2"]
    assert plan["update"] == []
    assert plan["delete"] == []
    assert plan["skip"] == []
