from app.rag.query_processor import QueryProcessor, extract_filters, looks_like_followup, to_vnd
from app.rag.types import HistoryTurn
from tests.unit.fakes import FakeLLM


def test_to_vnd():
    assert to_vnd("50", "k") == 50_000
    assert to_vnd("50.000", None) == 50_000
    assert to_vnd("1,5", "tr") == 1_500_000
    assert to_vnd("50", None) == 50_000        # không đơn vị, < 1000 => nghìn
    assert to_vnd("40", "nghin") == 40_000


def test_price_filters():
    assert extract_filters("món cơm dưới 50k") == {"max_price": 49_999}      # "dưới" loại mốc
    assert extract_filters("mon duoi 50.000đ") == {"max_price": 49_999}
    assert extract_filters("rẻ hơn 40 nghìn") == {"max_price": 39_999}
    assert extract_filters("tối đa 70k") == {"max_price": 70_000}
    assert extract_filters("trên 1,5tr") == {"min_price": 1_500_001}
    assert extract_filters("tối thiểu 30k") == {"min_price": 30_000}       # "tối thiểu" gồm mốc
    assert extract_filters("từ 30k đến 50k") == {"min_price": 30_000, "max_price": 50_000}
    assert extract_filters("từ 30 đến 50k") == {"min_price": 30_000, "max_price": 50_000}   # đơn vị lan sang số đầu
    assert extract_filters("cơm gà còn hàng không") == {}


def test_order_id_filter():
    assert extract_filters("Đơn #123 của tôi đâu")["order_id"] == "123"
    assert extract_filters("mã đơn 4567")["order_id"] == "4567"
    assert "order_id" not in extract_filters("đơn hàng của tôi")


def test_followup_detection():
    assert looks_like_followup("Còn món nào rẻ hơn?")
    assert looks_like_followup("món đó có cay không")
    assert not looks_like_followup("Chính sách hoàn tiền của cửa hàng như thế nào vậy bạn")


HIST = [HistoryTurn("user", "Cơm gà xối mỡ giá bao nhiêu?"), HistoryTurn("assistant", "45.000đ")]


async def test_rewrite_followup():
    llm = FakeLLM(answer='"Có món cơm nào rẻ hơn Cơm gà xối mỡ dưới 45k không?"')
    pq = await QueryProcessor(llm).process("Còn món nào rẻ hơn?", HIST)
    assert pq.rewritten and pq.standalone.startswith("Có món cơm nào rẻ hơn")
    assert pq.filters["max_price"] == 44_999 and pq.original == "Còn món nào rẻ hơn?"


async def test_no_rewrite_without_history_or_followup():
    llm = FakeLLM(answer="x")
    qp = QueryProcessor(llm)
    assert (await qp.process("Còn món nào rẻ hơn?", [])).standalone == "Còn món nào rẻ hơn?"
    long_q = "Chính sách hoàn tiền của cửa hàng như thế nào vậy bạn"
    assert (await qp.process(long_q, HIST)).standalone == long_q
    assert llm.calls == 0


async def test_rewrite_failure_falls_back_to_original():
    pq = await QueryProcessor(FakeLLM(fail=True)).process("Còn món nào rẻ hơn?", HIST)
    assert pq.standalone == "Còn món nào rẻ hơn?" and not pq.rewritten


async def test_without_llm_followup_with_cue_is_concatenated_with_previous_question():
    pq = await QueryProcessor(None).process("Còn món nào rẻ hơn?", HIST)
    assert pq.rewritten and pq.standalone == "Cơm gà xối mỡ giá bao nhiêu? Còn món nào rẻ hơn?"
    pq2 = await QueryProcessor(None).process("Món này còn hàng không?", HIST)
    assert pq2.standalone.startswith("Cơm gà xối mỡ giá bao nhiêu?")


async def test_without_llm_no_concatenation_for_greetings_or_standalone_questions():
    qp = QueryProcessor(None)
    for question in ("Xin chào", "cảm ơn nhé", "Hủy đơn thế nào?", "Phí giao hàng bao nhiêu"):
        pq = await qp.process(question, HIST)
        assert pq.standalone == question and not pq.rewritten, question
    assert (await qp.process("Còn món nào rẻ hơn?", [])).standalone == "Còn món nào rẻ hơn?"     # không có lịch sử


async def test_carried_over_is_reported_only_when_a_previous_question_was_concatenated():
    qp = QueryProcessor(None)
    pq = await qp.process("Còn món nào rẻ hơn?", HIST)
    assert pq.carried_over == "Cơm gà xối mỡ giá bao nhiêu?"
    assert (await qp.process("Hủy đơn thế nào?", HIST)).carried_over is None
    assert (await qp.process("Còn món nào rẻ hơn?", [])).carried_over is None


def test_followup_cue_ignores_time_words_like_hom_nay():
    from app.rag.query_processor import has_followup_cue
    assert not has_followup_cue("Giá bitcoin hôm nay")                # "hôm nay" = today, không phải "này"
    assert not has_followup_cue("Hôm nay có món gì?") and not has_followup_cue("Tuần này có khuyến mãi gì")
    assert has_followup_cue("Món này còn hàng không?") and has_followup_cue("mon nay con hang khong")
    assert has_followup_cue("Đơn đó giao chưa") and has_followup_cue("Còn món nào rẻ hơn?")


async def test_offtopic_question_is_never_glued_to_previous_context():
    hist = [HistoryTurn("user", "Đơn #123 của tôi đang ở đâu?"), HistoryTurn("assistant", "Đơn đang được giao.")]
    for question in ("Giá bitcoin hôm nay", "Viết giúp mình đoạn code python này", "hello nay"):
        pq = await QueryProcessor(None).process(question, hist)
        assert pq.standalone == question and pq.carried_over is None, question