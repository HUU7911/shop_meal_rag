"""Chạy golden set và tính metric (xem eval/README.md).

    python -m eval.run_eval --mode intent                  # không cần hạ tầng: guardrail + router + luật
    python -m eval.run_eval --mode retrieval --k 4         # cần Qdrant + model embedding (KHÔNG cần LLM)
    python -m eval.run_eval --mode full --judge            # cần Qdrant + LLM; --judge chấm độ phủ ý bằng LLM
Tuỳ chọn so sánh cấu hình:  --no-rerank  --no-hybrid  --limit N  --golden path.jsonl

Mỗi lần chạy ghi eval/reports/<timestamp>.json kèm cấu hình để so trước/sau.
Hạn chế đã biết: mode intent bỏ qua rewrite nên với câu có history chỉ đánh giá câu gốc;
mode full không có Product/Order Service thật nên câu sản phẩm/đơn hàng có thể ra UPSTREAM_DOWN.
"""
import argparse
import asyncio
import json
import re
import statistics
import time
from datetime import datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.errors import GuardrailBlocked
from app.rag.guardrails import Guardrails
from app.rag.intent_router import IntentRouter
from app.rag.query_processor import QueryProcessor
from app.rag.types import HistoryTurn, RAGRequest, RAGUser
from app.rag.utils import apply_score_threshold
from eval.metrics import best_rerank_scores, threshold_sweep, top_rerank_scores
from app.schemas.chat_schema import Intent

ROOT = Path(__file__).resolve().parent
RETRIEVAL_TYPES = {"FAQ_POLICY": ["FAQ", "POLICY", "DOCUMENT"], "PRODUCT_SEARCH": ["PRODUCT"], "PRODUCT_DETAIL": ["PRODUCT"]}


def load_golden(path: Path, limit: int | None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def pct(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d else 0.0


def history_of(row: dict) -> list[HistoryTurn]:
    return [HistoryTurn(h["role"], h["content"]) for h in row.get("history", [])]


# ---------------- intent ----------------
async def eval_intent(rows: list[dict], settings) -> dict:
    """Guardrail -> QueryProcessor (nối câu nối tiếp theo luật, giống bot thật) -> router."""
    guard, router, qp = Guardrails(max_length=settings.message_max_length), IntentRouter(), QueryProcessor(None)
    results = []
    for r in rows:
        try:
            question = guard.check_input(r["question"])
            pq = await qp.process(question, history_of(r))
            predicted = router.route(pq.standalone, pq.filters).value
        except GuardrailBlocked:
            predicted = Intent.OUT_OF_SCOPE.value
        results.append({"id": r["id"], "question": r["question"], "expected": r["expected_intent"],
                        "predicted": predicted, "ok": predicted == r["expected_intent"]})
    by_intent: dict[str, dict] = {}
    for x in results:
        b = by_intent.setdefault(x["expected"], {"n": 0, "ok": 0})
        b["n"] += 1
        b["ok"] += x["ok"]
    return {"accuracy_pct": pct(sum(x["ok"] for x in results), len(results)), "n": len(results),
            "by_expected_intent": {k: f"{v['ok']}/{v['n']}" for k, v in sorted(by_intent.items())},
            "errors": [x for x in results if not x["ok"]]}


# ---------------- retrieval ----------------
def _brief(hits) -> list[str]:
    return [f"{h.document_id}(s={h.score:.3f}" + (f",r={h.rerank_score:.3f}" if h.rerank_score is not None else "") + ")"
            for h in hits]


async def eval_retrieval(rows: list[dict], settings, k: int) -> dict:
    """Mô phỏng đúng đường truy xuất của bot: QueryProcessor -> retriever -> rerank -> NGƯỠNG ĐIỂM.

    Chỉ số tổng (theo ngưỡng hiện tại):
      hit@k / mrr      : chunk đúng có trong top-k (trước ngưỡng) — chất lượng XẾP HẠNG.
      answerable_pct   : chunk đúng còn sống SAU ngưỡng.
      top1_correct_pct : chunk đầu tiên SAU ngưỡng là chunk đúng -> bot trả lời ĐÚNG (chế độ không LLM trả chunk đầu).
      false_accept_pct : câu KB không có đáp án (expect_no_context) mà bot vẫn trả lời nội dung khác.
    Phân loại lỗi (khác nhau về mức nguy hiểm):
      found_but_below_threshold : chunk đúng có trong top-k nhưng bị ngưỡng loại, KHÔNG còn chunk nào -> bot nói "chưa có thông tin" (an toàn).
      wrong_chunk_first         : bot có chunk để trả lời nhưng chunk đầu KHÔNG đúng -> trả lời SAI chủ đề (nguy hiểm hơn).
    `threshold_sweep` cho biết 3 loại kết quả (đúng / sai / không trả lời) và false-accept theo từng ngưỡng để CHỌN ngưỡng.
    Giả định router đúng (dùng expected_intent chọn loại nội dung); độ chính xác router đo riêng ở --mode intent.
    """
    from app.rag.factory import build_retrieval_stack
    client, _embedder, retriever, reranker = await build_retrieval_stack(settings)
    qp, drop_rrf = QueryProcessor(None), not settings.llm_enabled

    async def run(r: dict):
        pq = await qp.process(r["question"], history_of(r))
        hits = await retriever.search(pq.standalone, content_types=RETRIEVAL_TYPES.get(r["expected_intent"]),
                                      filters=pq.filters, top_k=settings.retrieval_top_k)
        limit = getattr(settings, "rerank_candidates", 0)
        hits = (await asyncio.to_thread(reranker.rerank, pq.standalone, hits[:limit] if limit else hits, k)
                if reranker.enabled else hits[:k])
        kept, _dropped = apply_score_threshold(hits, settings.retrieval_score_threshold, drop_unscored_rrf=drop_rrf)
        return hits, kept

    scored = [r for r in rows if r.get("expected_doc_ids")]
    refusals = [r for r in rows if r.get("expect_no_context")]
    in_topk = answerable = top1 = 0
    reciprocal, latencies, misses, below_threshold, wrong_first, false_accepts = [], [], [], [], [], []
    scored_rows, refusal_rows = [], []
    for r in scored:
        started = time.perf_counter()
        hits, kept = await run(r)
        latencies.append((time.perf_counter() - started) * 1000)
        expected = set(r["expected_doc_ids"])
        scored_rows.append((expected, hits))
        rank = next((i for i, h in enumerate(hits, 1) if h.document_id in expected), None)
        in_topk += rank is not None
        reciprocal.append(1 / rank if rank else 0.0)
        answerable += any(h.document_id in expected for h in kept)
        top1 += bool(kept) and kept[0].document_id in expected
        entry = {"id": r["id"], "question": r["question"], "expected": sorted(expected), "got": _brief(hits),
                 "got_titles": [h.title for h in hits]}
        if rank is None:
            misses.append(entry)
        elif not kept:
            below_threshold.append(entry)
        elif kept[0].document_id not in expected:
            wrong_first.append({**entry, "bot_would_answer_with": _brief(kept)})
    for r in refusals:
        hits, kept = await run(r)
        refusal_rows.append(hits)
        if kept:
            false_accepts.append({"id": r["id"], "question": r["question"], "answered_with": _brief(kept),
                                  "answered_titles": [h.title for h in kept]})
    await client.close()
    n = len(scored)
    result = {"k": k, "n_scored": n, "n_refusal_cases": len(refusals), f"hit@{k}_pct": pct(in_topk, n),
              "mrr": round(sum(reciprocal) / n, 3) if n else 0.0,
              "answerable_pct": pct(answerable, n), "top1_correct_pct": pct(top1, n),
              "false_accept_pct": pct(len(false_accepts), len(refusals)),
              "threshold": settings.retrieval_score_threshold,
              "latency_ms_p50": round(statistics.median(latencies)) if latencies else 0,
              "latency_ms_p95": round(sorted(latencies)[int(0.95 * (len(latencies) - 1))]) if latencies else 0,
              "rerank_max_length": getattr(settings, "rerank_max_length", 512),
              "rerank_candidates": getattr(settings, "rerank_candidates", 0)}
    if reranker.enabled:
        result["threshold_sweep"] = threshold_sweep(scored_rows, refusal_rows)
        result["rerank_score_of_correct_chunk"] = best_rerank_scores(scored_rows)
        result["rerank_top_score_of_refusal_cases"] = top_rerank_scores(refusal_rows)
    result.update({"misses_not_in_topk": misses, "found_but_below_threshold": below_threshold,
                   "wrong_chunk_first": wrong_first, "false_accepts": false_accepts})
    return result


# ---------------- full ----------------
_JUDGE_SYSTEM = ("Bạn chấm câu trả lời của chatbot. Với MỖI ý trong danh sách 'ý cần có', trả true nếu câu trả lời "
                 'thể hiện đúng ý đó, ngược lại false. Chỉ trả JSON: {"covered":[true,false,...]}')


async def judge(llm, answer: str, points: list[str]) -> float | None:
    prompt = f"Câu trả lời:\n{answer}\n\nÝ cần có:\n" + "\n".join(f"{i + 1}. {p}" for i, p in enumerate(points))
    text, _ = await llm.generate([{"role": "system", "content": _JUDGE_SYSTEM}, {"role": "user", "content": prompt}],
                                 max_tokens=120, temperature=0.0)
    match = re.search(r"\{.*\}", text, re.S)
    try:
        covered = json.loads(match.group(0))["covered"] if match else []
    except (ValueError, KeyError):
        return None
    return sum(bool(c) for c in covered) / len(points) if covered and len(covered) == len(points) else None


async def eval_full(rows: list[dict], settings, k: int, use_judge: bool) -> dict:
    from app.integrations.order_client import OrderClient
    from app.integrations.product_client import ProductClient
    from app.rag.factory import build_rag_engine
    engine, close = await build_rag_engine(settings, ProductClient(), OrderClient())
    if use_judge and engine.llm is None:
        print("(--judge cần LLM_ENABLED=true; đang ở chế độ không LLM nên bỏ qua chấm điểm bằng LLM)")
        use_judge = False
    guest, details = RAGUser(user_id=None), []
    intent_ok = fallback_ok = fallback_n = 0
    coverage, latencies, tokens = [], [], []
    for r in rows:
        history = [HistoryTurn(h["role"], h["content"]) for h in r.get("history", [])]
        res = await engine.invoke(RAGRequest(r["question"], history, guest, f"eval-{r['id']}"))
        intent_ok += res.intent.value == r["expected_intent"]
        if "expected_fallback" in r:
            fallback_n += 1
            fallback_ok += res.fallback_reason == r["expected_fallback"]
        latencies.append(res.trace.latency_ms.get("total", 0))
        tokens.append(res.trace.usage.prompt_tokens + res.trace.usage.completion_tokens)
        score = None
        if use_judge and r.get("expected_answer_points") and not res.fallback_reason:
            score = await judge(engine.llm, res.answer, r["expected_answer_points"])
            if score is not None:
                coverage.append(score)
        details.append({"id": r["id"], "intent": res.intent.value, "fallback": res.fallback_reason,
                        "coverage": score, "answer": res.answer[:200]})
    await close()
    n = len(rows)
    return {"n": n, "intent_accuracy_pct": pct(intent_ok, n), "fallback_correct_pct": pct(fallback_ok, fallback_n),
            "answer_point_coverage": round(sum(coverage) / len(coverage), 3) if coverage else None,
            "latency_ms_p50": round(statistics.median(latencies)) if latencies else 0,
            "tokens_avg": round(statistics.mean(tokens)) if tokens else 0, "details": details}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["intent", "retrieval", "full"], default="intent")
    ap.add_argument("--golden", type=Path, default=ROOT / "golden_set.jsonl")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--judge", action="store_true")
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--no-hybrid", action="store_true")
    args = ap.parse_args()

    settings = get_settings().model_copy(update={
        **({"rerank_enabled": False} if args.no_rerank else {}),
        **({"hybrid_enabled": False} if args.no_hybrid else {})})
    rows = load_golden(args.golden, args.limit)
    if args.mode == "intent":
        metrics = asyncio.run(eval_intent(rows, settings))
    elif args.mode == "retrieval":
        metrics = asyncio.run(eval_retrieval(rows, settings, args.k))
    else:
        metrics = asyncio.run(eval_full(rows, settings, args.k, args.judge))

    report = {"timestamp": datetime.now().isoformat(timespec="seconds"), "mode": args.mode,
              "config": {"embedding_model": settings.embedding_model, "hybrid": settings.hybrid_enabled,
                         "rerank": settings.rerank_enabled, "rerank_model": settings.rerank_model,
                         "top_k": settings.retrieval_top_k, "rerank_top_n": settings.rerank_top_n,
                         "threshold": settings.retrieval_score_threshold, "llm_model": settings.llm_model},
              "metrics": metrics}
    out = ROOT / "reports" / f"{args.mode}-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in metrics.items() if k not in ("details",)}, ensure_ascii=False, indent=2))
    print(f"\nĐã ghi {out}")


if __name__ == "__main__":
    main()