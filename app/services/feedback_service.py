"""Lưu feedback theo message_id; thống kê theo lý do/intent."""


class FeedbackService:
    async def submit(self, user_id: str | None, request) -> str:
        raise NotImplementedError  # TODO(Member 01)
