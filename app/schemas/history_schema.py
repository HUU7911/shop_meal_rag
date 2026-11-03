from datetime import datetime
from enum import StrEnum

from app.schemas.chat_schema import SourceItem
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
    sources: list[SourceItem] = []
    created_at: datetime


class ConversationHistoryResponse(CamelModel):
    conversation_id: str
    messages: list[MessageItem]
