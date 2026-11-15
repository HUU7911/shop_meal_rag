from app.rag.answer_generator import TemplateAnswerGenerator, asks_ingredients
from app.rag.tools.common import order_data, product_data
from app.rag.types import Hit, ToolResult
from app.schemas.chat_schema import Intent, SourceType
from tests.unit.fakes import order, product

gen = TemplateAnswerGenerator("CSKH Shop Meal")


def faq(doc, question, answer, score=0.9):
    return Hit(chunk_id=doc, document_id=doc, content_type="FAQ", title=question, score=score,
               text=f"Câu hỏi: {question}\nTrả lời: {answer}")


def policy(index, heading, body):
    return Hit(chunk_id=f"p{index}", document_id="cancellation", content_type="POLICY", title="Chính sách hủy đơn",
               text=f"Chính sách hủy đơn > {heading}\n{body}", score=0.9, payload={"chunk_index": index})


def tool(info=None, ord_=None):
    if info is not None:
        return ToolResult("product_detail", SourceType.PRODUCT, info.product_id, info.name, "x", data=product_data(info))
    return ToolResult("order_status", SourceType.ORDER, ord_.order_id, "Đơn", "x", data=order_data(ord_))


def test_faq_returns_only_the_answer_part_and_related_questions():
    out = gen.generate(intent=Intent.FAQ_POLICY, question="đặt hàng", tool_results=[], hits=[
        faq("f1", "Làm thế nào để đặt hàng?", "Chọn món rồi thanh toán."),
        faq("f2", "Có hủy đơn được không?", "Được."), faq("f1", "Làm thế nào để đặt hàng?", "trùng")])
    assert out.startswith("Chọn món rồi thanh toán.") and "Câu hỏi:" not in out
    assert "Có hủy đơn được không?" in out and out.count("Làm thế nào để đặt hàng?") == 0


def test_policy_sections_of_same_document_in_chunk_order():
    out = gen.generate(intent=Intent.FAQ_POLICY, question="hủy đơn", tool_results=[], hits=[
        policy(1, "Hoàn tiền", "Hoàn về phương thức ban đầu."), policy(0, "Điều kiện hủy", "Khi chưa xác nhận.")])
    assert out.startswith("Theo Chính sách hủy đơn:")
    assert out.index("Điều kiện hủy") < out.index("Hoàn tiền") and "Chính sách hủy đơn >" not in out


def test_product_detail_uses_live_data_and_status_phrase():
    ok = gen.generate(intent=Intent.PRODUCT_DETAIL, question="còn hàng không", hits=[], tool_results=[tool(product())])
    assert "45.000đ" in ok and "đang còn hàng" in ok
    out_of_stock = gen.generate(intent=Intent.PRODUCT_DETAIL, question="còn hàng không", hits=[],
                                tool_results=[tool(product(status="OUT_OF_STOCK"))])
    assert "hiện đã hết hàng" in out_of_stock


def test_product_search_lists_items():
    items = [tool(product("p1", "Cơm gà", 45000)), tool(product("p2", "Trà đào", 30000))]
    out = gen.generate(intent=Intent.PRODUCT_SEARCH, question="món dưới 50k", hits=[], tool_results=items)
    assert "2 món" in out and "- Cơm gà — 45.000đ" in out and "- Trà đào — 30.000đ" in out


def test_ingredient_questions_never_make_claims():
    assert asks_ingredients("Món này có chứa đậu phộng không?") and asks_ingredients("thanh phan mon nay")
    assert not asks_ingredients("Cơm gà còn hàng không?") and not asks_ingredients("giá của món này")
    for intent in (Intent.PRODUCT_DETAIL, Intent.PRODUCT_SEARCH):
        out = gen.generate(intent=intent, question="Món này có chứa đậu phộng không?", hits=[],
                           tool_results=[tool(product())])
        assert "chưa có thông tin chi tiết" in out and "CSKH Shop Meal" in out
        assert "không chứa" not in out and "có chứa" not in out


def test_order_summary():
    out = gen.generate(intent=Intent.ORDER_STATUS, question="đơn #123", hits=[], tool_results=[tool(ord_=order("123", "DELIVERING"))])
    assert "Đơn #123 đang được giao" in out and "100" not in out.replace("90.000đ", "") and "90.000đ" in out
    assert "Cơm gà x2" in out
    unknown = gen.generate(intent=Intent.ORDER_STATUS, question="đơn #5", hits=[],
                           tool_results=[tool(ord_=order("5", "WEIRD_CODE"))])
    assert "có trạng thái WEIRD_CODE" in unknown