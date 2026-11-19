from app.services.history_trim import trim_history


def tok(text: str) -> int:
    return len(text)          # 1 ký tự = 1 token cho dễ tính


def msgs(*pairs):
    out = []
    for i, content in enumerate(pairs):
        out.append({"role": "user" if i % 2 == 0 else "assistant", "content": content})
    return out


def test_keeps_everything_within_budget():
    m = msgs("a", "b", "c", "d")
    assert trim_history(m, max_messages=12, max_tokens=100, count_tokens=tok) == m


def test_limits_by_message_count_and_starts_with_user():
    m = msgs("q1", "a1", "q2", "a2", "q3", "a3")
    out = trim_history(m, max_messages=3, max_tokens=100, count_tokens=tok)
    # 3 message mới nhất = a2, q3, a3 -> bỏ a2 mồ côi ở đầu
    assert [x["content"] for x in out] == ["q3", "a3"]


def test_limits_by_tokens_prefers_newest():
    m = msgs("q1xxxx", "a1xxxx", "q2", "a2")
    out = trim_history(m, max_messages=12, max_tokens=6, count_tokens=tok)
    assert [x["content"] for x in out] == ["q2", "a2"]


def test_oversized_newest_message_is_truncated_not_dropped():
    m = msgs("câu hỏi", "x" * 100)
    out = trim_history(m, max_messages=12, max_tokens=10, count_tokens=tok)
    # assistant mới nhất bị cắt; user trước đó không còn chỗ -> assistant mồ côi bị bỏ -> rỗng
    assert out == []
    m2 = msgs("y" * 100)
    out2 = trim_history(m2, max_messages=12, max_tokens=10, count_tokens=tok)
    assert len(out2) == 1 and len(out2[0]["content"]) == 10


def test_zero_budget_returns_empty():
    assert trim_history(msgs("a", "b"), max_messages=0, max_tokens=10, count_tokens=tok) == []
    assert trim_history(msgs("a", "b"), max_messages=4, max_tokens=0, count_tokens=tok) == []
