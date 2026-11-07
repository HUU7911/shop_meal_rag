"""Chạy ingestion: load -> clean -> plan (registry) -> chunk -> embed -> upsert -> switch alias.
Idempotent: chạy lại nhiều lần không tạo dữ liệu trùng. Một tài liệu lỗi không làm hỏng cả job.
"""
import logging
from typing import Any

from app.core.config import get_settings
from app.ingestion.chunking import chunk_faq, chunk_policy
from app.ingestion.cleaner import clean_record
from app.ingestion.indexing import Indexer
from app.ingestion.loaders.faq_loader import FAQLoader
from app.ingestion.loaders.policy_loader import PolicyLoader
from app.ingestion.payload import ChunkPayload

log = logging.getLogger("app.ingestion.pipeline")


async def run(mode: str = "incremental") -> dict[str, Any]:
    settings = get_settings()
    indexer = Indexer(settings=settings)

    if mode == "verify":
        collection = f"{settings.qdrant_collection}_v1"
        try:
            count = await indexer.count_points(collection)
            aliases = {a.alias_name: a.collection_name for a in (await indexer.client.get_aliases()).aliases}
            active_alias = aliases.get(settings.qdrant_collection)
            return {
                "status": "ok",
                "collection": collection,
                "points_count": count,
                "alias": settings.qdrant_collection,
                "alias_target": active_alias,
            }
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # 1. Load raw records
    log.info("Bắt đầu nạp dữ liệu (mode=%s)...", mode)
    faq_raw = FAQLoader().load()
    policy_raw = PolicyLoader().load()

    # 2. Clean & Chunk
    all_chunks: list[ChunkPayload] = []

    # Clean & chunk FAQ
    clean_faq_count = 0
    for r in faq_raw:
        cleaned = clean_record(r)
        if cleaned:
            chunks = chunk_faq(cleaned)
            all_chunks.extend(chunks)
            clean_faq_count += 1

    # Clean & chunk Policies
    clean_policy_count = 0
    for r in policy_raw:
        cleaned = clean_record(r)
        if cleaned:
            chunks = chunk_policy(cleaned["content"], cleaned)
            all_chunks.extend(chunks)
            clean_policy_count += 1

    log.info("Đã tạo được tổng cộng %d chunks (FAQ: %d, Policies: %d)",
             len(all_chunks), clean_faq_count, clean_policy_count)

    # 3. Index into Qdrant
    target_collection = await indexer.ensure_collection("v1")
    upserted_count = await indexer.upsert(target_collection, all_chunks)

    # 4. Switch alias to point to the newly updated collection
    await indexer.switch_alias(settings.qdrant_collection, target_collection)

    await indexer.client.close()

    result = {
        "status": "success",
        "mode": mode,
        "collection": target_collection,
        "alias": settings.qdrant_collection,
        "faq_documents": clean_faq_count,
        "policy_documents": clean_policy_count,
        "total_chunks_indexed": len(all_chunks),
        "total_points_upserted": upserted_count,
    }
    log.info("Ingestion hoàn thành: %s", result)
    return result
