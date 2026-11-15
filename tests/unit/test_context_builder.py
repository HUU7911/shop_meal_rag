from app.rag.context_builder import ContextBuilder
from app.rag.types import ToolResult
from app.schemas.chat_schema import SourceType
from tests.unit.fakes import faq_hit

cb = ContextBuilder()


def tool(ok=True, found=True, text="Cơm gà — giá 45.000đ"):
    return ToolResult("product_detail", SourceType.PRODUCT, "p1", "Cơm gà", text, ok=ok, found=found)


def test_tool_results_come_first_and_have_sources():
    built = cb.build([faq_hit()], [tool()], 1000)
    assert built.text.startswith("[1] (Dữ liệu trực tiếp)") and "[2] (POLICY)" in built.text
    assert {(s.type, s.id) for s in built.sources} == {(SourceType.PRODUCT, "p1"), (SourceType.POLICY, "cancellation")}
    assert built.has_context


def test_dedup_chunks_and_single_source_per_document():
    a, b = faq_hit(score=0.5), faq_hit(score=0.9, text="Nội dung khác.")
    built = cb.build([a, faq_hit(score=0.5), b], [], 1000)
    assert built.text.count("(POLICY)") == 2            # bản trùng bị loại
    assert len(built.sources) == 1 and built.sources[0].score == 0.9


def test_failed_tool_adds_note_but_no_source_and_no_context():
    built = cb.build([], [tool(ok=False, found=False, text="Không kiểm tra được.")], 1000)
    assert "Lưu ý hệ thống" in built.text and built.sources == [] and not built.has_context


def test_not_found_tool_has_no_source():
    built = cb.build([], [tool(found=False, text="Không thấy đơn.")], 1000)
    assert built.sources == [] and not built.has_context


def test_token_budget_truncates():
    big = [faq_hit(doc=f"d{i}", text="x" * 600) for i in range(10)]
    built = cb.build(big, [], 500)
    assert 1 <= built.text.count("[") <= 3
    first_only = cb.build([faq_hit(text="y" * 5000)], [], 100)
    assert first_only.text and len(first_only.text) <= 400


def test_tool_source_keeps_url_when_chunk_of_same_product_has_higher_score():
    chunk = faq_hit(doc="p1", content_type="PRODUCT", score=0.9)
    built = cb.build([chunk], [tool()], 1000)
    (source,) = [s for s in built.sources if s.id == "p1"]
    assert source.title == "Cơm gà" and source.score == 0.9      # thông tin của tool, điểm của chunk


def test_tool_url_is_preserved():
    t = ToolResult("product_detail", SourceType.PRODUCT, "p1", "Cơm gà", "giá 45.000đ", url="/products/p1")
    built = cb.build([faq_hit(doc="p1", content_type="PRODUCT", score=0.9)], [t], 1000)
    assert built.sources[0].url == "/products/p1"
