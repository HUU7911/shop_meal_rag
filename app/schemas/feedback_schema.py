from enum import StrEnum

from pydantic import Field

from app.schemas.common_schema import CamelModel


class Rating(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"


class FeedbackReason(StrEnum):
    INACCURATE = "INACCURATE"
    IRRELEVANT = "IRRELEVANT"
    NOT_FOUND = "NOT_FOUND"
    OTHER = "OTHER"


class FeedbackRequest(CamelModel):
    conversation_id: str
    message_id: str
    rating: Rating
    reason: FeedbackReason | None = None
    comment: str | None = Field(default=None, max_length=1000)


class FeedbackResponse(CamelModel):
    feedback_id: str
    accepted: bool = True
