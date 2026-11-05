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
from app.rag.query_processor import extract_filters
from app.rag.types import HistoryTurn, RAGRequest, RAGUser
from app.schemas.chat_schema import Intent

ROOT = Path(__file__).resolve().parent
RETRIEVAL_TYPES = {"FAQ_POLICY": ["FAQ", "POLICY", "DOCUMENT"], "PRODUCT_SEARCH": ["PRODUCT"], "PRODUCT_DETAIL": ["PRODUCT"]}


def load_golden(path: Path, limit: int | None) -> list[dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[:limit] if limit else rows


def pct(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d else 0.0


# ---------------- intent ----------------
def eval_intent(rows: list[dict], settings) -> dict:
    guard, router, results = Guardrails(max_length=settings.message_max_length), IntentRouter(), []
    for r in rows:
        try:
            guard.check_input(r["question"])
            predicted = router.route(r["question"], extract_filters(r["question"])).value
        except GuardrailBlocked:
            predicted = Intent.OUT_OF_SCOPE.value
        results.append({"id": r["id"], "expected": r["expected_intent"], "predicted": predicted,
                        "ok": predicted == r["expected_intent"]})
    ok = sum(x["ok"] for x in results)
    return {"accuracy_pct": pct(ok, len(results)), "n": len(results),
            "errors": [x for x in results if not x["ok"]]}


# ---------------- retrieval ----------------
async def eval_retrieval(rows: list[dict], settings, k: int) -> dict:
    from app.rag.factory import build_retrieval_stack
    client, _embedder, retriever, reranker = await build_retrieval_stack(settings)
    hits_at_k, reciprocal, details, latencies = 0, [], [], []
    scored = [r for r in rows if r.get("expected_doc_ids")]
    for r in scored:
        question, intent = r["question"], r["expected_intent"]
        started = time.perf_counter()
        hits = await retriever.search(question, content_types=RETRIEVAL_TYPES.get(intent),
                                      filters=extract_filters(question), top_k=settings.retrieval_top_k)
        hits = await asyncio.to_thread(reranker.rerank, question, hits, k) if reranker.enabled else hits[:k]
        latencies.append((time.perf_counter() - started) * 1000)
        expected, rank = set(r["expected_doc_ids"]), None
        for i, h in enumerate(hits, 1):
            if h.document_id in expected:
                rank = i
                break
        hits_at_k += rank is not None
        reciprocal.append(1 / rank if rank else 0.0)
        details.append({"id": r["id"], "rank": rank, "got": [h.document_id for h in hits],
                        "expected": sorted(expected)})
    await client.close()
    n = len(scored)
    return {"k": k, "n": n, f"hit@{k}_pct": pct(hits_at_k, n),
            "mrr": round(sum(reciprocal) / n, 3) if n else 0.0,
            "latency_ms_p50": round(statistics.median(latencies)) if latencies else 0,
            "misses": [d for d in details if d["rank"] is None]}


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
        metrics = eval_intent(rows, settings)
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
