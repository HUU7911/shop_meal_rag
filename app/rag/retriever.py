"""Truy xuất từ Qdrant: hybrid (dense + sparse, RRF) hoặc dense-only, luôn kèm payload filter.

BẮT BUỘC (hợp đồng, docs/CONTRACTS.md §3):
  * enabled == true
  * effective_date rỗng HOẶC <= now   (policy hết/chưa hiệu lực không được trả về)
Điểm số: dense -> cosine (score_kind="cosine"); hybrid -> RRF (score_kind="rrf", KHÔNG so với ngưỡng cosine).
"""
import asyncio
import logging
from datetime import datetime, timezone

from qdrant_client import AsyncQdrantClient, models

from app.core.errors import ConfigurationError, EmbeddingError, RetrievalError, VectorDatabaseError
from app.embedding.embedding_service import EmbeddingService
from app.ingestion.payload import point_id
from app.rag.types import Hit

log = logging.getLogger("app.rag.retriever")

PREFETCH_LIMIT = 20


def build_filter(content_types: list[str] | None, category: str | None = None,
                 now: datetime | None = None) -> models.Filter:
    now = now or datetime.now(timezone.utc)
    must: list = [
        models.FieldCondition(key="enabled", match=models.MatchValue(value=True)),
        models.Filter(should=[
            models.IsNullCondition(is_null=models.PayloadField(key="effective_date")),
            models.FieldCondition(key="effective_date", range=models.DatetimeRange(lte=now)),
        ]),
    ]
    if content_types:
        must.append(models.FieldCondition(key="content_type", match=models.MatchAny(any=content_types)))
    if category:
        must.append(models.FieldCondition(key="category", match=models.MatchValue(value=category)))
    return models.Filter(must=must)


class Retriever:
    def __init__(self, client: AsyncQdrantClient, embedder: EmbeddingService, *, collection: str,
                 hybrid_enabled: bool = True, top_k: int = 8):
        self.client, self.embedder, self.collection = client, embedder, collection
        self.hybrid_enabled, self.top_k = hybrid_enabled, top_k

    async def verify(self) -> None:
        """Gọi lúc khởi động: kiểm tra collection khớp EmbeddingService (kích thước vector, sparse)."""
        try:
            info = await self.client.get_collection(self.collection)
        except Exception as exc:  # noqa: BLE001
            raise VectorDatabaseError(f"Không đọc được collection '{self.collection}': {exc}") from exc
        vectors = info.config.params.vectors
        dense = vectors.get("dense") if isinstance(vectors, dict) else None
        if dense is None:
            raise ConfigurationError(f"Collection '{self.collection}' thiếu named vector 'dense'")
        if dense.size != self.embedder.dim:
            raise ConfigurationError(
                f"Lệch kích thước vector: collection={dense.size}, EMBEDDING_DIM={self.embedder.dim}. "
                "Cần index lại bằng collection mới (xem docs/CONTRACTS.md §3).")
        if self.hybrid_enabled and not (info.config.params.sparse_vectors or {}).get("sparse"):
            log.warning("Collection chưa có vector 'sparse' -> hybrid sẽ không dùng được, chạy dense-only")
        # Điểm META (tuỳ chọn, do ingestion ghi): xác nhận đúng tên model.
        try:
            meta = await self.client.retrieve(self.collection, ids=[point_id("META", "kb", 0)],
                                              with_payload=True, with_vectors=False)
        except Exception:  # noqa: BLE001
            meta = []
        if meta:
            built_with = meta[0].payload.get("embedding_model")
            if built_with and built_with != self.embedder.model_name:
                raise ConfigurationError(
                    f"Collection build bằng '{built_with}' nhưng đang dùng '{self.embedder.model_name}'")
        else:
            log.warning("Không thấy điểm META của KB: chỉ kiểm tra được kích thước vector, chưa kiểm tra được tên model")

    async def search(self, question: str, *, content_types: list[str] | None = None,
                     filters: dict | None = None, top_k: int | None = None) -> list[Hit]:
        top_k = top_k or self.top_k
        try:
            encoded = await asyncio.to_thread(self.embedder.embed_query, question)
        except EmbeddingError:
            raise
        flt = build_filter(content_types, (filters or {}).get("category"))
        use_hybrid = self.hybrid_enabled and encoded.has_sparse
        try:
            if use_hybrid:
                response = await self.client.query_points(
                    collection_name=self.collection,
                    prefetch=[
                        models.Prefetch(query=encoded.dense, using="dense", limit=PREFETCH_LIMIT, filter=flt),
                        models.Prefetch(
                            query=models.SparseVector(indices=encoded.sparse_indices, values=encoded.sparse_values),
                            using="sparse", limit=PREFETCH_LIMIT, filter=flt),
                    ],
                    query=models.FusionQuery(fusion=models.Fusion.RRF),
                    limit=top_k, with_payload=True)
            else:
                response = await self.client.query_points(
                    collection_name=self.collection, query=encoded.dense, using="dense",
                    query_filter=flt, limit=top_k, with_payload=True)
        except Exception as exc:  # noqa: BLE001
            raise VectorDatabaseError(f"Qdrant truy vấn lỗi: {exc}") from exc
        return [self._to_hit(p, "rrf" if use_hybrid else "cosine") for p in response.points]

    @staticmethod
    def _to_hit(point, score_kind: str) -> Hit:
        payload = dict(point.payload or {})
        try:
            return Hit(chunk_id=str(payload.get("chunk_id") or point.id),
                       document_id=str(payload["document_id"]),
                       content_type=str(payload.get("content_type", "")),
                       title=str(payload.get("title", "")), text=str(payload.get("text", "")),
                       score=float(point.score), score_kind=score_kind, payload=payload)
        except KeyError as exc:
            raise RetrievalError(f"Chunk thiếu trường bắt buộc {exc} (vi phạm payload contract)") from exc
