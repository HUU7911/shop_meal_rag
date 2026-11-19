from app.core.errors import NotFoundError, PermissionDenied
from app.core.ids import new_id
from app.db.models.chat import Conversation
from app.db.unit_of_work import UnitOfWorkFactory
from app.schemas.common_schema import Page
from app.schemas.history_schema import ConversationItem


async def get_owned_conversation(repository, user_id: str | None, conversation_id: str) -> Conversation:
    """Lấy conversation và KIỂM TRA CHỦ SỞ HỮU (dùng chung cho chat/history/feedback).

    Khách (user_id=None) chỉ truy cập được conversation của khách; id là chuỗi ngẫu nhiên 128-bit
    nên đóng vai trò bí mật. Người đã đăng nhập không truy cập được conversation của người khác/khách.
    """
    conversation = await repository.get_by_id(conversation_id)
    if conversation is None:
        raise NotFoundError("Không tìm thấy cuộc trò chuyện.")
    if conversation.user_id != user_id:
        raise PermissionDenied("Bạn không có quyền truy cập cuộc trò chuyện này.")
    return conversation


def to_item(conversation: Conversation) -> ConversationItem:
    return ConversationItem(
        conversation_id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


class ConversationService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self._uow = uow_factory

    async def get_or_create(
        self,
        user_id: str | None,
        conversation_id: str | None,
    ) -> Conversation:
        """Tạo conversation mới nếu chưa có ID, ngược lại kiểm tra tồn tại + quyền sở hữu."""
        async with self._uow() as uow:
            if conversation_id is None:
                return await uow.conversations.create(
                    Conversation(id=new_id("c"), user_id=user_id, title=None)
                )
            return await get_owned_conversation(uow.conversations, user_id, conversation_id)

    async def create(self, user_id: str) -> ConversationItem:
        conversation = await self.get_or_create(user_id, None)
        return to_item(conversation)

    async def list(self, user_id: str, page: int, page_size: int) -> Page[ConversationItem]:
        async with self._uow() as uow:
            rows, total = await uow.conversations.list_by_user(
                user_id, offset=(page - 1) * page_size, limit=page_size
            )
            items = [to_item(c) for c in rows]
        return Page[ConversationItem](items=items, page=page, page_size=page_size, total=total)
