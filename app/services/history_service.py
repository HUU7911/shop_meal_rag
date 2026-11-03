"""Đọc/ghi lịch sử. Redis cache N lượt gần nhất; MySQL là nguồn sự thật.

Cắt lịch sử theo token budget (HISTORY_MAX_TOKENS), ưu tiên giữ các lượt mới nhất.
"""


class HistoryService:
    async def recent(self, conversation_id: str) -> list[dict]:
        raise NotImplementedError  # TODO(Member 01)

    async def save_turn(self, conversation_id: str, user_text: str, result) -> str:
        """Lưu cặp message, trả `message_id` của câu trả lời. Lưu cả sources và trace."""
        raise NotImplementedError
