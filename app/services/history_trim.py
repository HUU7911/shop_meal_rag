"""Cắt lịch sử theo ngân sách (HISTORY_MAX_TURNS / HISTORY_MAX_TOKENS). Hàm thuần, không phụ thuộc I/O."""
from collections.abc import Callable


def trim_history(
    messages: list[dict],
    *,
    max_messages: int,
    max_tokens: int,
    count_tokens: Callable[[str], int],
) -> list[dict]:
    """`messages` theo thứ tự cũ -> mới, mỗi phần tử {"role", "content"}.

    * giữ tối đa `max_messages` message mới nhất và tổng token <= `max_tokens` (ưu tiên lượt mới nhất)
    * message mới nhất mà một mình đã vượt ngân sách -> cắt bớt nội dung thay vì bỏ (giữ ngữ cảnh
      cho câu hỏi nối tiếp)
    * kết quả luôn bắt đầu bằng message của `user` (không để câu trả lời mồ côi ở đầu)
    """
    if max_messages <= 0 or max_tokens <= 0:
        return []
    kept: list[dict] = []
    used = 0
    for msg in reversed(messages[-max_messages:]):
        content = msg["content"]
        tokens = count_tokens(content)
        if used + tokens > max_tokens:
            if kept:
                break
            keep_chars = max(1, int(len(content) * max_tokens / max(tokens, 1)))
            content, tokens = content[:keep_chars], max_tokens
        kept.append({"role": msg["role"], "content": content})
        used += tokens
    kept.reverse()
    while kept and kept[0]["role"] != "user":
        kept.pop(0)
    return kept
