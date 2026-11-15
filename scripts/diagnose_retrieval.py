"""Chẩn đoán truy xuất cho MỘT câu hỏi: in điểm thô ở từng tầng, KHÔNG gọi LLM.

    python -m scripts.diagnose_retrieval "Làm sao để đặt hàng?"
    python -m scripts.diagnose_retrieval "Còn hàng không?" --types PRODUCT

In ra: (1) dense-only (cosine) (2) hybrid (RRF) (3) điểm rerank của kết quả hybrid
       (4) điểm rerank THỬ NGHIỆM khi bỏ dấu cả câu hỏi lẫn nội dung (để kiểm tra giả thuyết
           "reranker chấm kém câu hỏi không dấu").
Dùng để hiệu chỉnh RETRIEVAL_SCORE_THRESHOLD và để biết chunk bị loại ở bước nào.
"""
import argparse
import asyncio
import dataclasses

from app.core.config import get_settings
from app.rag.factory import build_retrieval_stack
from app.rag.utils import strip_accents


def show(title: str, hits) -> None:
    print(f"\n== {title} ({len(hits)}) ==")
    for h in hits:
        rr = f"  rerank={h.rerank_score:.3f}" if h.rerank_score is not None else ""
        print(f"  {h.score:8.4f} [{h.score_kind}] {h.content_type:8} {h.document_id:24} {h.title[:50]}{rr}")


async def main(question: str, types: list[str] | None) -> None:
    settings = get_settings()
    client, _embedder, retriever, reranker = await build_retrieval_stack(settings)
    print(f"Câu hỏi: {question}\nLoại nội dung: {types or 'tất cả'}   ngưỡng hiện tại: {settings.retrieval_score_threshold}")

    retriever.hybrid_enabled = False
    show("DENSE-ONLY", await retriever.search(question, content_types=types, top_k=8))
    retriever.hybrid_enabled = settings.hybrid_enabled
    hybrid = await retriever.search(question, content_types=types, top_k=8)
    show("HYBRID (RRF)", hybrid)
    if reranker.enabled and hybrid:
        reranked = await asyncio.to_thread(reranker.rerank, question, hybrid, len(hybrid))
        show("SAU RERANK (điểm rerank so với ngưỡng)", reranked)
        plain_hits = [dataclasses.replace(h, title=strip_accents(h.title), text=strip_accents(h.text),
                                          rerank_score=None) for h in hybrid]
        plain = await asyncio.to_thread(reranker.rerank, strip_accents(question), plain_hits, len(plain_hits))
        show("RERANK THỬ NGHIỆM: bỏ dấu cả câu hỏi và nội dung", plain)
    await client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--types", nargs="*", help="FAQ POLICY PRODUCT DOCUMENT")
    args = ap.parse_args()
    asyncio.run(main(args.question, args.types))