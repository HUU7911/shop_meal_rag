from eval.metrics import best_rerank_scores, threshold_sweep, top_rerank_scores
from tests.unit.fakes import faq_hit


def hit(doc, rerank):
    h = faq_hit(doc=doc)
    h.rerank_score = rerank
    return h


# Hit đã sắp giảm dần theo rerank_score (đúng như Reranker.rerank trả về)
SCORED = [
    ({"a"}, [hit("a", 0.9), hit("x", 0.01)]),        # chunk đúng điểm cao
    ({"b"}, [hit("b", 0.12), hit("x", 0.01)]),       # chunk đúng nhưng điểm thấp (câu diễn đạt khác)
    ({"c"}, [hit("x", 0.30), hit("c", 0.02)]),       # chunk SAI đứng đầu, chunk đúng điểm thấp
]
REFUSALS = [[hit("x", 0.08)], [hit("y", 0.02)]]      # KB không có đáp án; điểm cao nhất 0.08 và 0.02


def row(t):
    return next(r for r in threshold_sweep(SCORED, REFUSALS, grid=(t,)))


def test_sweep_three_way_split_and_false_accept():
    high = row(0.5)       # chỉ chunk a qua
    assert (high["correct_first_pct"], high["wrong_answer_pct"], high["no_answer_pct"], high["false_accept_pct"]) \
        == (33.3, 0.0, 66.7, 0.0)
    mid = row(0.1)        # thêm b (đúng) nhưng cũng cho chunk sai x(0.30) đứng đầu ở câu c, và x(0.08) không qua
    assert (mid["correct_first_pct"], mid["wrong_answer_pct"], mid["no_answer_pct"]) == (66.7, 33.3, 0.0)
    assert mid["false_accept_pct"] == 0.0
    low = row(0.05)       # hạ thấp: câu "KB không có đáp án" đầu tiên (0.08) bắt đầu lọt qua -> trả lời lạc đề
    assert low["false_accept_pct"] == 50.0 and low["wrong_answer_pct"] == 33.3


def test_score_summaries_show_the_gap_the_threshold_must_fit_in():
    assert best_rerank_scores(SCORED) == [0.9, 0.12, 0.02]
    assert top_rerank_scores(REFUSALS) == [0.08, 0.02]
    assert best_rerank_scores([({"z"}, [hit("x", 0.5)])]) == [None]      # chunk đúng không có trong top-k