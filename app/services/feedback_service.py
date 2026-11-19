"""Lưu feedback theo message_id. Mỗi user chỉ có 1 feedback cho 1 câu trả lời (gửi lại = cập nhật)."""
from app.core.errors import NotFoundError, ValidationFailed
from app.core.ids import new_id
from app.db.models.chat import Feedback
from app.db.unit_of_work import UnitOfWorkFactory
from app.schemas.feedback_schema import FeedbackRequest, Rating
from app.services.conversation_service import get_owned_conversation


class FeedbackService:
    def __init__(self, uow_factory: UnitOfWorkFactory):
        self._uow = uow_factory

    async def submit(self, user_id: str | None, request: FeedbackRequest) -> str:
        """Trả feedback_id. Message phải là câu trả lời của chatbot trong conversation của chính user."""
        async with self._uow() as uow:
            message = await uow.messages.get_by_id(request.message_id)
            if message is None or message.conversation_id != request.conversation_id:
                raise NotFoundError("Không tìm thấy tin nhắn.")
            await get_owned_conversation(uow.conversations, user_id, message.conversation_id)
            if message.role != "assistant":
                raise ValidationFailed("Chỉ có thể đánh giá câu trả lời của chatbot.")

            reason = request.reason.value if request.reason and request.rating is Rating.NEGATIVE else None
            existing = await uow.feedback.get_by_message_and_user(message.id, user_id)
            if existing is not None:
                existing.rating = request.rating.value
                existing.reason = reason
                existing.comment = request.comment
                return existing.id

            feedback = await uow.feedback.add(
                Feedback(
                    id=new_id("f"), message_id=message.id, user_id=user_id,
                    rating=request.rating.value, reason=reason, comment=request.comment,
                )
            )
            return feedback.id
