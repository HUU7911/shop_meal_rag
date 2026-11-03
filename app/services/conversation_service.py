"""Tạo conversation, kiểm tra quyền sở hữu, sinh title, soft delete."""


class ConversationService:
    async def get_or_create(self, user_id: str | None, conversation_id: str | None):
        raise NotImplementedError  # TODO(Member 01)
