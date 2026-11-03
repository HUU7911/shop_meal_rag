"""HỢP ĐỒNG PAYLOAD QDRANT (Member 03 ⇄ Member 02). Xem docs/CONTRACTS.md §3."""
import hashlib
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import StrEnum

NAMESPACE = uuid.UUID("6f1d2c5e-8a4b-4f0e-9a52-0c7d3b1e5a11")


class ContentType(StrEnum):
    FAQ = "FAQ"
    POLICY = "POLICY"
    PRODUCT = "PRODUCT"
    DOCUMENT = "DOCUMENT"


# Các trường cần tạo payload index trong Qdrant
INDEXED_FIELDS = {
    "content_type": "keyword",
    "category": "keyword",
    "enabled": "bool",
    "effective_date": "datetime",
    "product_id": "keyword",
}


def point_id(content_type: ContentType, source_id: str, chunk_index: int) -> str:
    """ID ổn định -> upsert idempotent, xóa được theo (content_type, source_id)."""
    return str(uuid.uuid5(NAMESPACE, f"{content_type}:{source_id}:{chunk_index}"))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class ChunkPayload:
    chunk_id: str
    document_id: str
    content_type: str
    title: str
    text: str                      # giá/trạng thái sản phẩm KHÔNG được đưa vào text embed
    chunk_index: int
    content_hash: str
    updated_at: str
    enabled: bool = True
    category: str | None = None
    version: str | None = None
    effective_date: str | None = None
    source_url: str | None = None
    # Riêng PRODUCT (chỉ để lọc thô, trả lời phải lấy live)
    product_id: str | None = None
    product_type: str | None = None
    status_snapshot: str | None = None
    price_snapshot: float | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"
