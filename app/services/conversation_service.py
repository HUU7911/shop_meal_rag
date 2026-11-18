from uuid import uuid4

from app.core.errors import NotFoundError, PermissionDenied
from app.db.models.chat import Conversation
from app.db.repositories.conversation_repository import ConversationRepository


class ConversationService:
    def __init__(self, repository: ConversationRepository):
        self.repository = repository

    async def get_or_create(
        self,
        user_id: str | None,
        conversation_id: str | None,
    ) -> Conversation:
        # Tạo conversation mới nếu chưa có ID.
        if conversation_id is None:
            conversation = Conversation(
                id=uuid4().hex,
                user_id=user_id,
                title=None,
            )
            return await self.repository.create(conversation)

        # Tìm conversation hiện tại.
        conversation = await self.repository.get_by_id(conversation_id)

        if conversation is None:
            raise NotFoundError("Không tìm thấy cuộc trò chuyện.")

        # Kiểm tra quyền sở hữu.
        if conversation.user_id != user_id:
            raise PermissionDenied("Bạn không có quyền truy cập cuộc trò chuyện này.")

        return conversation
