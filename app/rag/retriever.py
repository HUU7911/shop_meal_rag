"""Truy xuất từ Qdrant: hybrid (dense + sparse, RRF) + payload filter.

BẮT BUỘC luôn áp filter: enabled == true  VÀ  (effective_date IS NULL HOẶC <= now);
policy lấy version mới nhất. Lọc thêm theo content_type/category từ ProcessedQuery.filters.
Khởi động: kiểm tra metadata collection (embedding_model, dim) khớp EmbeddingService.
"""


class Retriever:
    async def search(self, standalone_question: str, *, content_types: list[str] | None = None,
                     filters: dict | None = None, top_k: int = 8) -> list[dict]:
        raise NotImplementedError  # TODO(Member 02)
