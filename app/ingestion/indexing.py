"""Ghi vào Qdrant.

- Tạo collection `shop_meal_knowledge_v{N}` (named vectors `dense` + `sparse`) và payload index
  theo `payload.INDEXED_FIELDS`; ghi metadata (embedding_model, dim, kb_version, built_at).
- Upsert theo batch với id từ `payload.point_id`.
- Full reindex: build collection mới -> kiểm tra số lượng -> đổi alias `QDRANT_COLLECTION` -> giữ bản cũ để rollback.
- Xóa: theo filter (content_type, document_id) khi nguồn bị xóa/disable.
"""


class Indexer:
    async def ensure_collection(self, version: str) -> str:
        raise NotImplementedError  # TODO(Member 03)

    async def upsert(self, collection: str, chunks: list) -> None:
        raise NotImplementedError

    async def delete_document(self, collection: str, content_type: str, document_id: str) -> None:
        raise NotImplementedError

    async def switch_alias(self, alias: str, collection: str) -> None:
        raise NotImplementedError
