from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class CamelModel(BaseModel):
    """Mọi schema API dùng camelCase ra ngoài, snake_case trong code."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ErrorBody(CamelModel):
    code: str
    message: str
    request_id: str | None = None


class ErrorResponse(CamelModel):
    error: ErrorBody


class PaginationRequest(CamelModel):
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class Page(CamelModel, Generic[T]):
    items: list[T]
    page: int
    page_size: int
    total: int


class Timestamped(CamelModel):
    created_at: datetime
    updated_at: datetime | None = None
