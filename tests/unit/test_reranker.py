from app.rag.reranker import Reranker
from tests.unit.fakes import faq_hit


class FakeCrossEncoder:
    def __init__(self):
        self.pairs = None

    def predict(self, pairs):
        self.pairs = pairs
        return [0.9 if "xac nhan" in doc else 0.1 for _q, doc in pairs]   # chỉ chunk thân bài khớp (cả hai cùng tiêu đề)


def make():
    r = Reranker("unused", enabled=False)       # không nạp model thật
    r.enabled, r._model = True, FakeCrossEncoder()
    return r


def hits():
    return [faq_hit(doc="x", text="Thanh toán online qua ví."),
            faq_hit(doc="cancellation", text="Khách có thể hủy đơn khi chưa xác nhận.")]


def test_unaccented_query_is_scored_on_unaccented_text_but_results_keep_original_text():
    r = make()
    out = r.rerank("co the huy don khong", hits(), 2)
    query, doc = r._model.pairs[1]
    assert query == "co the huy don khong" and "huy don" in doc and "hủy" not in doc
    assert out[0].document_id == "cancellation" and out[0].rerank_score == 0.9
    assert "hủy đơn" in out[0].text                      # nội dung trả về vẫn có dấu


def test_accented_query_is_scored_unchanged():
    r = make()
    r.rerank("Có thể hủy đơn không?", hits(), 2)
    query, doc = r._model.pairs[1]
    assert query == "Có thể hủy đơn không?" and "hủy đơn" in doc