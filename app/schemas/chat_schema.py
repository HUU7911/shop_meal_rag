from enum import StrEnum

from pydantic import Field, field_validator

from app.schemas.common_schema import CamelModel


class Intent(StrEnum):
    FAQ_POLICY = "FAQ_POLICY"
    PRODUCT_SEARCH = "PRODUCT_SEARCH"
    PRODUCT_DETAIL = "PRODUCT_DETAIL"
    ORDER_STATUS = "ORDER_STATUS"
    SMALLTALK = "SMALLTALK"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class SourceType(StrEnum):
    FAQ = "FAQ"
    POLICY = "POLICY"
    PRODUCT = "PRODUCT"
    DOCUMENT = "DOCUMENT"
    ORDER = "ORDER"


class ChatRequest(CamelModel):
    # id do server sinh ("c_" + 32 hex = 34 ký tự); giới hạn khớp cột conversations.id
    conversation_id: str | None = Field(default=None, max_length=40)
    # Trần cứng 4000 ở đây; giới hạn thực tế settings.message_max_length do API kiểm tra (422)
    message: str = Field(min_length=1, max_length=4000)

    @field_validator("conversation_id", mode="before")
    @classmethod
    def _blank_conversation_id_is_none(cls, v):
        # Frontend đôi khi gửi "" thay vì null ở lượt đầu
        return None if isinstance(v, str) and not v.strip() else v

    @field_validator("message")
    @classmethod
    def _message_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message không được để trống")
        return v


class SourceItem(CamelModel):
    type: SourceType
    id: str
    title: str
    snippet: str | None = None
    url: str | None = None
    score: float | None = None


class ChatMetadata(CamelModel):
    model: str | None = None
    prompt_version: str | None = None
    retrieval_count: int = 0
    fallback: str | None = None


class ChatResponse(CamelModel):
    conversation_id: str
    message_id: str                      # bắt buộc: Feedback tham chiếu theo message_id
    answer: str
    intent: Intent
    sources: list[SourceItem] = []
    metadata: ChatMetadata = ChatMetadata()
