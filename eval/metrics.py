"""Các phép tính thuần cho eval (không import gì nặng nên test được ngay).

`threshold_sweep` trả lời câu hỏi "nên đặt RETRIEVAL_SCORE_THRESHOLD bao nhiêu?" bằng dữ liệu: với mỗi ngưỡng t, giữ các chunk
có rerank_score >= t rồi phân loại kết quả của từng câu hỏi:
  correct_first : chunk đầu tiên giữ lại là chunk đúng        (bot trả lời ĐÚNG)
  wrong_answer  : có giữ chunk nhưng chunk đầu không đúng      (bot trả lời SAI chủ đề  -> lỗi nguy hiểm)
  no_answer     : không giữ chunk nào                          (bot nói "chưa có thông tin" -> lỗi an toàn)
  false_accept  : với câu KB không có đáp án mà vẫn giữ được chunk (bot trả lời lạc đề)
Chỉ có nghĩa khi reranker bật (hits đã sắp xếp giảm dần theo rerank_score).
"""
GRID = (0.02, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5)


def _kept(hits, t):
    return [h for h in hits if h.rerank_score is not None and h.rerank_score >= t]


def threshold_sweep(scored_rows, refusal_rows, grid=GRID) -> list[dict]:
    """scored_rows: [(expected_doc_ids:set, hits)], refusal_rows: [hits]."""
    out = []
    for t in grid:
        correct = wrong = 0
        for expected, hits in scored_rows:
            kept = _kept(hits, t)
            if kept and kept[0].document_id in expected:
                correct += 1
            elif kept:
                wrong += 1
        n = len(scored_rows)
        false_accept = sum(1 for hits in refusal_rows if _kept(hits, t))
        pct = lambda a, b: round(100 * a / b, 1) if b else 0.0
        out.append({"threshold": t, "correct_first_pct": pct(correct, n), "wrong_answer_pct": pct(wrong, n),
                    "no_answer_pct": pct(n - correct - wrong, n), "false_accept_pct": pct(false_accept, len(refusal_rows))})
    return out


def best_rerank_scores(scored_rows):
    """Điểm rerank của chunk ĐÚNG (cao nhất trong số chunk đúng) cho từng câu; None nếu chunk đúng không có trong top-k."""
    out = []
    for expected, hits in scored_rows:
        scores = [h.rerank_score for h in hits if h.document_id in expected and h.rerank_score is not None]
        out.append(round(max(scores), 3) if scores else None)
    return out


def top_rerank_scores(refusal_rows):
    """Điểm rerank cao nhất của từng câu 'KB không có đáp án' — đây là mức mà ngưỡng phải VƯỢT QUA để từ chối đúng."""
    return [round(max((h.rerank_score or 0.0) for h in hits), 3) if hits else 0.0 for hits in refusal_rows]