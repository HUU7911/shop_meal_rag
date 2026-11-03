from enum import StrEnum

from pydantic import Field

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
    conversation_id: str | None = None
    # Giới hạn độ dài thực tế được kiểm tra thêm theo settings.message_max_length
    message: str = Field(min_length=1, max_length=4000)


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
