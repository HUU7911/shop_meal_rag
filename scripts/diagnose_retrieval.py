"""Chẩn đoán truy xuất cho MỘT câu hỏi: in thứ hạng và điểm ở từng tầng, KHÔNG gọi LLM.

    python -m scripts.diagnose_retrieval "Làm sao để đặt hàng?" --types FAQ POLICY
    python -m scripts.diagnose_retrieval "<câu hỏi>" --types FAQ POLICY --top-k 47 --expect faq-support-003

  --top-k N     số kết quả mỗi tầng (mặc định = RETRIEVAL_TOP_K). Đặt bằng số chunk của KB để thấy TOÀN BỘ bảng xếp hạng.
  --expect ID   document_id đáng lẽ phải thắng: đánh dấu "<<< ĐÚNG" và in bảng TÓM TẮT thứ hạng ở từng tầng,
                để biết chunk đúng bị mất ở đâu (tìm kiếm vòng đầu hay rerank).
Ba tầng: dense-only (cosine) -> hybrid (RRF) -> sau rerank (điểm so với RETRIEVAL_SCORE_THRESHOLD).
"""
import argparse
import asyncio

from app.core.config import get_settings
from app.rag.factory import build_retrieval_stack


def rank_of(hits, doc_id: str | None):
    return next((i for i, h in enumerate(hits, 1) if h.document_id == doc_id), None)


def show(title: str, hits, expect: str | None = None) -> None:
    print(f"\n== {title} ({len(hits)}) ==")
    for i, h in enumerate(hits, 1):
        rr = f"  rerank={h.rerank_score:.3f}" if h.rerank_score is not None else ""
        mark = "   <<< ĐÚNG" if expect and h.document_id == expect else ""
        print(f"  {i:2}. {h.score:8.4f} [{h.score_kind}] {h.content_type:8} {h.document_id:24} {h.title[:50]}{rr}{mark}")


async def main(question: str, types: list[str] | None, top_k: int | None, expect: str | None) -> None:
    settings = get_settings()
    client, _embedder, retriever, reranker = await build_retrieval_stack(settings)
    k = top_k or settings.retrieval_top_k
    print(f"Câu hỏi: {question}\nLoại nội dung: {types or 'tất cả'}   top_k: {k}   ngưỡng hiện tại: "
          f"{settings.retrieval_score_threshold}   rerank trên: {reranker.device_in_use}")

    retriever.hybrid_enabled = False
    dense = await retriever.search(question, content_types=types, top_k=k)
    retriever.hybrid_enabled = settings.hybrid_enabled
    hybrid = await retriever.search(question, content_types=types, top_k=k)
    show("DENSE-ONLY (cosine)", dense, expect)
    show("HYBRID (RRF)", hybrid, expect)
    reranked = []
    if reranker.enabled and hybrid:
        reranked = await asyncio.to_thread(reranker.rerank, question, hybrid, len(hybrid))
        show("SAU RERANK (điểm rerank so với ngưỡng)", reranked, expect)

    if expect:
        print(f"\n== TÓM TẮT: chunk đúng '{expect}' nằm ở đâu ==")
        for name, hits in (("dense-only", dense), ("hybrid", hybrid), ("sau rerank", reranked)):
            r = rank_of(hits, expect)
            score = next((h.rerank_score for h in hits if h.document_id == expect and h.rerank_score is not None), None)
            print(f"  {name:11}: " + (f"hạng {r}/{len(hits)}" + (f", điểm rerank {score:.3f}" if score is not None else "")
                                      if r else f"KHÔNG có trong {len(hits)} kết quả"))
    await client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--types", nargs="*", help="FAQ POLICY PRODUCT DOCUMENT")
    ap.add_argument("--top-k", type=int)
    ap.add_argument("--expect", help="document_id đáng lẽ phải thắng")
    a = ap.parse_args()
    asyncio.run(main(a.question, a.types, a.top_k, a.expect))