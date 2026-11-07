"""Ghi vào Qdrant (Indexer).

- Tạo collection `shop_meal_knowledge_v{N}` (named vectors `dense` + `sparse`) và payload index
  theo `payload.INDEXED_FIELDS`; ghi metadata (embedding_model, dim, kb_version, built_at).
- Upsert theo batch với id từ `payload.point_id`.
- Full reindex: build collection mới -> kiểm tra số lượng -> đổi alias `QDRANT_COLLECTION` -> giữ bản cũ để rollback.
- Xóa: theo filter (content_type, document_id) khi nguồn bị xóa/disable.
"""
import asyncio
import logging

from qdrant_client import AsyncQdrantClient, models

from app.core.config import Settings, get_settings
from app.core.errors import VectorDatabaseError
from app.embedding.embedding_service import EmbeddingService
from app.ingestion.payload import INDEXED_FIELDS, ChunkPayload, now_iso, point_id

log = logging.getLogger("app.ingestion.indexer")

_SCHEMA_MAP = {
    "keyword": models.PayloadSchemaType.KEYWORD,
    "bool": models.PayloadSchemaType.BOOL,
    "datetime": models.PayloadSchemaType.DATETIME,
}


class Indexer:
    def __init__(self, settings: Settings | None = None, client: AsyncQdrantClient | None = None,
                 embedder: EmbeddingService | None = None):
        self.s = settings or get_settings()
        api_key = self.s.qdrant_api_key.get_secret_value() or None
        self.client = client or AsyncQdrantClient(url=self.s.qdrant_url, api_key=api_key)
        self.embedder = embedder

    def _get_embedder(self) -> EmbeddingService:
        if self.embedder is None:
            self.embedder = EmbeddingService(self.s.embedding_model, self.s.embedding_dim, self.s.embedding_device)
        return self.embedder

    async def ensure_collection(self, version: str = "v1") -> str:
        """Đảm bảo collection tồn tại, có đủ named vectors và payload index."""
        collection_name = f"{self.s.qdrant_collection}_{version}"
        try:
            exists = await self.client.collection_exists(collection_name)
            if not exists:
                log.info("Tạo mới collection Qdrant: %s", collection_name)
                sparse_cfg = models.SparseVectorParams() if self._get_embedder().supports_sparse else None
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config={"dense": models.VectorParams(size=self.s.embedding_dim, distance=models.Distance.COSINE)},
                    sparse_vectors_config={"sparse": sparse_cfg} if sparse_cfg else None,
                )
                for field, kind in INDEXED_FIELDS.items():
                    await self.client.create_payload_index(
                        collection_name=collection_name,
                        field_name=field,
                        field_schema=_SCHEMA_MAP[kind],
                    )
            return collection_name
        except Exception as exc:
            log.error("Lỗi ensure_collection '%s': %s", collection_name, exc, exc_info=True)
            raise VectorDatabaseError(f"Không thể khởi tạo collection '{collection_name}': {exc}") from exc

    async def upsert(self, collection: str, chunks: list[ChunkPayload], batch_size: int = 64) -> int:
        """Embed và upsert danh sách chunks vào Qdrant."""
        if not chunks:
            return 0

        embedder = self._get_embedder()
        texts_to_embed = [c.embed_text or c.text for c in chunks]

        log.info("Bắt đầu sinh embedding cho %d chunks...", len(chunks))
        encoded_list = await asyncio.to_thread(embedder.embed_documents, texts_to_embed)

        points = []
        for chunk, enc in zip(chunks, encoded_list):
            vector: dict = {"dense": enc.dense}
            if enc.has_sparse:
                vector["sparse"] = models.SparseVector(indices=enc.sparse_indices, values=enc.sparse_values)
            points.append(models.PointStruct(id=chunk.chunk_id, vector=vector, payload=chunk.to_dict()))

        # Điểm META của collection (enabled=false để không bao giờ bị retrieve)
        meta_vec = [1.0] + [0.0] * (self.s.embedding_dim - 1)
        points.append(models.PointStruct(
            id=point_id("META", "kb", 0),
            vector={"dense": meta_vec},
            payload={
                "enabled": False,
                "content_type": "META",
                "document_id": "META",
                "embedding_model": self.s.embedding_model,
                "embedding_dim": self.s.embedding_dim,
                "built_at": now_iso(),
            },
        ))

        # Đẩy theo batch
        total_upserted = 0
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await self.client.upsert(collection_name=collection, points=batch, wait=True)
            total_upserted += len(batch)

        log.info("Upsert thành công %d điểm vào collection '%s'", total_upserted, collection)
        return total_upserted

    async def delete_document(self, collection: str, content_type: str, document_id: str) -> None:
        """Xóa toàn bộ các chunk của một tài liệu dựa vào content_type và document_id."""
        flt = models.Filter(must=[
            models.FieldCondition(key="content_type", match=models.MatchValue(value=content_type)),
            models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id)),
        ])
        await self.client.delete(collection_name=collection, points_selector=models.FilterSelector(filter=flt), wait=True)
        log.info("Đã xóa document '%s' (type=%s) khỏi '%s'", document_id, content_type, collection)

    async def switch_alias(self, alias: str, collection: str) -> None:
        """Đổi alias sang collection mới sau khi reindex hoàn tất (zero downtime)."""
        aliases = {a.alias_name for a in (await self.client.get_aliases()).aliases}
        ops = []
        if alias in aliases:
            ops.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias)))
        ops.append(models.CreateAliasOperation(create_alias=models.CreateAlias(collection_name=collection, alias_name=alias)))
        await self.client.update_collection_aliases(change_aliases_operations=ops)
        log.info("Đã trỏ alias '%s' -> '%s'", alias, collection)

    async def count_points(self, collection: str) -> int:
        """Đếm số point hiện có trong collection."""
        res = await self.client.count(collection_name=collection)
        return res.count
