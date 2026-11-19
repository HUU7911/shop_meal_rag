from datetime import datetime
from enum import StrEnum

from app.schemas.chat_schema import Intent, SourceItem
from app.schemas.common_schema import CamelModel


class Role(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ConversationItem(CamelModel):
    conversation_id: str
    title: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class MessageItem(CamelModel):
    message_id: str
    role: Role
    content: str
    intent: Intent | None = None
    sources: list[SourceItem] = []
    created_at: datetime


class ConversationHistoryResponse(CamelModel):
    conversation_id: str
    messages: list[MessageItem]
    # Phân trang (cũ -> mới). Thêm vào so với hợp đồng gốc: chỉ bổ sung trường, không phá tương thích.
    page: int = 1
    page_size: int = 50
    total: int = 0
