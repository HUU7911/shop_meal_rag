"""Seed TẠM FAQ + chính sách vào Qdrant để Member 02 làm việc khi Member 03 chưa xong ingestion.

    python -m scripts.seed_faq            # tạo/ghi vào shop_meal_knowledge_v1 và trỏ alias
    python -m scripts.seed_faq --recreate # xóa collection v1 rồi tạo lại

Khi ingestion thật xong thì BỎ script này. Cố ý đơn giản: không registry, không incremental.
Quy ước đã dùng đúng hợp đồng payload (app/ingestion/payload.py): id uuid5, enabled, document_id...
"""
import argparse
import asyncio
import json
import re
from pathlib import Path

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings
from app.embedding.embedding_service import EmbeddingService
from app.embedding.text_normalizer import normalize_text
from app.ingestion.payload import (INDEXED_FIELDS, ChunkPayload, ContentType, content_hash, now_iso,
                                   point_id)

DATA = Path(__file__).resolve().parent.parent / "data"
KB_VERSION = "v1"
_SCHEMA = {"keyword": models.PayloadSchemaType.KEYWORD, "bool": models.PayloadSchemaType.BOOL,
           "datetime": models.PayloadSchemaType.DATETIME}


def load_faq() -> list[tuple[ChunkPayload, str]]:
    """Trả về [(payload, embed_text)]: embed câu hỏi + keywords, payload.text chứa cả câu trả lời."""
    out = []
    for path in sorted((DATA / "faq").glob("*.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            text = f"Câu hỏi: {item['question']}\nTrả lời: {item['answer']}"
            embed = f"{item['question']} {' '.join(item.get('keywords', []))}"
            out.append((ChunkPayload(
                chunk_id=point_id(ContentType.FAQ, item["id"], 0), document_id=item["id"],
                content_type="FAQ", title=item["question"], text=text, chunk_index=0,
                content_hash=content_hash(text), updated_at=now_iso(), enabled=item.get("enabled", True),
                category=item.get("category")), embed))
    return out


def _front_matter(raw: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", raw, re.S)
    if not m:
        return {}, raw
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, m.group(2)


def load_policies() -> list[tuple[ChunkPayload, str]]:
    """Cắt theo heading '## ' (đơn giản hóa; chunking thật nằm ở ingestion của Member 03)."""
    out = []
    for path in sorted((DATA / "policies").glob("*.md")):
        meta, body = _front_matter(path.read_text(encoding="utf-8"))
        doc_id, title = meta.get("policy_id", path.stem), meta.get("title", path.stem)
        sections = [s.strip() for s in re.split(r"(?m)^## ", body) if s.strip()]
        for i, sec in enumerate(sections[1:] if len(sections) > 1 and sections[0].startswith("#") else sections):
            heading, _, content = sec.partition("\n")
            text = f"{title} > {heading.strip()}\n{content.strip()}"
            out.append((ChunkPayload(
                chunk_id=point_id(ContentType.POLICY, doc_id, i), document_id=doc_id, content_type="POLICY",
                title=title, text=text, chunk_index=i, content_hash=content_hash(text), updated_at=now_iso(),
                enabled=meta.get("enabled", "true").lower() == "true", version=meta.get("version"),
                effective_date=(meta["effective_date"] + "T00:00:00Z") if meta.get("effective_date") else None),
                text))
    return out


async def main(recreate: bool) -> None:
    s = get_settings()
    client = AsyncQdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key.get_secret_value() or None)
    embedder = EmbeddingService(s.embedding_model, s.embedding_dim, s.embedding_device)
    collection = f"{s.qdrant_collection}_{KB_VERSION}"

    if recreate and await client.collection_exists(collection):
        await client.delete_collection(collection)
    if not await client.collection_exists(collection):
        await client.create_collection(
            collection,
            vectors_config={"dense": models.VectorParams(size=s.embedding_dim, distance=models.Distance.COSINE)},
            sparse_vectors_config={"sparse": models.SparseVectorParams()})
        for field, kind in INDEXED_FIELDS.items():
            await client.create_payload_index(collection, field_name=field, field_schema=_SCHEMA[kind])

    rows = load_faq() + load_policies()
    encoded = await asyncio.to_thread(embedder.embed_documents, [normalize_text(e) for _, e in rows])
    points = []
    for (payload, _), enc in zip(rows, encoded):
        vector: dict = {"dense": enc.dense}
        if enc.has_sparse:
            vector["sparse"] = models.SparseVector(indices=enc.sparse_indices, values=enc.sparse_values)
        points.append(models.PointStruct(id=payload.chunk_id, vector=vector, payload=payload.to_dict()))
    # Điểm META (enabled=false nên không bao giờ được truy xuất): để Retriever.verify() kiểm tra tên model.
    meta_vec = [1.0] + [0.0] * (s.embedding_dim - 1)
    points.append(models.PointStruct(id=point_id("META", "kb", 0), vector={"dense": meta_vec}, payload={
        "enabled": False, "content_type": "META", "document_id": "META", "embedding_model": s.embedding_model,
        "embedding_dim": s.embedding_dim, "kb_version": KB_VERSION, "built_at": now_iso()}))
    await client.upsert(collection, points=points, wait=True)

    aliases = {a.alias_name for a in (await client.get_aliases()).aliases}
    ops = []
    if s.qdrant_collection in aliases:
        ops.append(models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=s.qdrant_collection)))
    ops.append(models.CreateAliasOperation(create_alias=models.CreateAlias(
        collection_name=collection, alias_name=s.qdrant_collection)))
    await client.update_collection_aliases(change_aliases_operations=ops)
    print(f"Đã nạp {len(rows)} chunk vào '{collection}' (alias '{s.qdrant_collection}')")
    await client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--recreate", action="store_true")
    asyncio.run(main(ap.parse_args().recreate))
