import json
from pathlib import Path

from app.rag.guardrails import Guardrails
from app.rag.intent_router import IntentRouter
from app.rag.query_processor import extract_filters
from app.schemas.chat_schema import Intent

GOLDEN = Path(__file__).resolve().parents[2] / "eval" / "golden_set.jsonl"
router = IntentRouter()


def route(q):
    return router.route(q, extract_filters(q))


def test_faq_vs_order_howto():
    assert route("Làm thế nào để xem trạng thái đơn hàng?") is Intent.FAQ_POLICY
    assert route("Đơn của tôi chưa được xác nhận thì có hủy được không?") is Intent.FAQ_POLICY
    assert route("lam sao de dat hang") is Intent.FAQ_POLICY


def test_order_status():
    assert route("Đơn #123 của tôi đang ở đâu?") is Intent.ORDER_STATUS
    assert route("don hang cua toi dang o dau") is Intent.ORDER_STATUS
    assert route("mã đơn 4567 giao chưa") is Intent.ORDER_STATUS


def test_product_intents():
    assert route("Có món cơm nào dưới 50k không?") is Intent.PRODUCT_SEARCH
    assert route("com ga xoi mo con hang khong") is Intent.PRODUCT_DETAIL
    assert route("Món này có chứa đậu phộng không?") is Intent.PRODUCT_DETAIL
    assert route("gợi ý món ăn nào ngon") is Intent.PRODUCT_SEARCH


def test_policy_words_not_confused_with_product():
    assert route("phí giao hàng bao nhiêu") is Intent.FAQ_POLICY        # 'giao' không khớp 'gia'
    assert route("thanh toan khi nhan hang duoc ko") is Intent.FAQ_POLICY


def test_generic_word_san_pham_does_not_hijack_policy_questions():
    assert route("Quy trình bảo hành sản phẩm như thế nào?") is Intent.FAQ_POLICY
    assert route("Có sản phẩm nào mới không?") is Intent.PRODUCT_SEARCH
    assert route("sản phẩm này giá bao nhiêu") is Intent.PRODUCT_DETAIL


def test_order_how_to_phrases_and_offtopic_before_product():
    assert route("dat mon online kieu gi") is Intent.FAQ_POLICY            # "mon" không được kéo sang sản phẩm
    assert route("Giá bitcoin hôm nay") is Intent.OUT_OF_SCOPE              # "giá" không phải hỏi giá món
    assert route("Cho mình hỏi đơn hàng của mình giao tới đâu rồi") is Intent.ORDER_STATUS


def test_promotions_are_policy_not_product_price():
    assert route("Có mã giảm giá hay khuyến mãi gì không?") is Intent.FAQ_POLICY      # "giá" trong "giảm giá"
    assert route("co voucher khong") is Intent.FAQ_POLICY
    assert route("Cơm gà xối mỡ giá bao nhiêu") is Intent.PRODUCT_DETAIL              # hỏi giá món vẫn đúng


def test_smalltalk_and_out_of_scope():
    assert route("Xin chào") is Intent.SMALLTALK
    assert route("cảm ơn bạn nhé") is Intent.SMALLTALK
    assert route("Hôm nay thời tiết thế nào?") is Intent.OUT_OF_SCOPE
    assert route("một câu hỏi lạ không rõ chủ đề") is Intent.FAQ_POLICY   # mặc định: để retrieval quyết định


async def test_golden_set_intents_via_guardrail_queryprocessor_and_router():
    """Cùng đường đi với `eval --mode intent` (có lịch sử, nối câu nối tiếp theo luật)."""
    from app.rag.query_processor import QueryProcessor
    from app.rag.types import HistoryTurn

    guard, qp, wrong = Guardrails(), QueryProcessor(None), []
    for line in GOLDEN.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        try:
            question = guard.check_input(row["question"])
            pq = await qp.process(question, [HistoryTurn(h["role"], h["content"]) for h in row.get("history", [])])
            got = router.route(pq.standalone, pq.filters)
        except Exception:
            got = Intent.OUT_OF_SCOPE
        if got.value != row["expected_intent"]:
            wrong.append((row["id"], row["question"], row["expected_intent"], got.value))
    assert not wrong, wrong