from app.rag.utils import lacks_diacritics


def test_lacks_diacritics():
    assert lacks_diacritics("co the huy don khong")
    assert lacks_diacritics("Dat hang") and lacks_diacritics("hello 123")
    assert not lacks_diacritics("Có thể hủy đơn không")
    assert not lacks_diacritics("đơn")
    assert not lacks_diacritics("đ")        # 'đ' cũng là dấu tiếng Việt


def test_apply_score_threshold_modes():
    from app.rag.utils import apply_score_threshold
    from tests.unit.fakes import faq_hit
    reranked = faq_hit(doc="a", score=0.1); reranked.rerank_score = 0.9
    low = faq_hit(doc="b", score=0.9); low.rerank_score = 0.1
    cosine_ok, cosine_low = faq_hit(doc="c", score=0.5), faq_hit(doc="d", score=0.2)
    rrf = faq_hit(doc="e", score=0.7, kind="rrf")
    kept, dropped = apply_score_threshold([reranked, low, cosine_ok, cosine_low, rrf], 0.35, drop_unscored_rrf=False)
    assert [h.document_id for h in kept] == ["a", "c", "e"] and [h.document_id for h in dropped] == ["b", "d"]
    kept, dropped = apply_score_threshold([rrf], 0.35, drop_unscored_rrf=True)      # chế độ không LLM
    assert kept == [] and dropped == [rrf]