"""Kiểm tra KB đang nằm trong Qdrant (alias QDRANT_COLLECTION) và (tuỳ chọn) sinh golden set từ FAQ.

    python -m scripts.audit_kb
    python -m scripts.audit_kb --write-golden eval/golden_kb.jsonl     # rồi: eval --mode retrieval --golden eval/golden_kb.jsonl

Thoát với mã 1 nếu có lỗi chặn (thiếu trường bắt buộc, trùng chunk, lệch model).
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from qdrant_client import AsyncQdrantClient

from app.core.config import get_settings
from eval.kb_audit import audit_payloads, build_golden_rows


async def scroll_all(client, collection: str) -> list[tuple]:
    items, offset = [], None
    while True:
        batch, offset = await client.scroll(collection, limit=256, offset=offset, with_payload=True, with_vectors=False)
        items.extend((p.id, p.payload or {}) for p in batch)
        if offset is None:
            return items


async def main(write_golden: Path | None) -> int:
    s = get_settings()
    client = AsyncQdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key.get_secret_value() or None)
    try:
        items = await scroll_all(client, s.qdrant_collection)
    finally:
        await client.close()
    report = audit_payloads(items, expected_model=s.embedding_model)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if write_golden:
        rows = build_golden_rows(items)
        write_golden.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
        print(f"\nĐã ghi {len(rows)} câu hỏi vào {write_golden} (chỉ dùng với --mode retrieval)")
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-golden", type=Path)
    sys.exit(asyncio.run(main(ap.parse_args().write_golden)))