"""Chat thử với RAGEngine ngay trên dòng lệnh (không cần API/Member 01).

    python -m scripts.chat_cli                  # khách (guest), dữ liệu sản phẩm/đơn hàng GIẢ
    python -m scripts.chat_cli --login          # giả lập người dùng đã đăng nhập (tra được đơn #123)
    python -m scripts.chat_cli --debug --stream # xem trace; phát token theo thời gian thực
    python -m scripts.chat_cli --real-clients   # dùng ProductClient/OrderClient thật (khi Member 01 xong)

Lệnh trong phiên: /reset (xóa lịch sử hội thoại)  /debug (bật/tắt trace)  /quit
Cần: Qdrant đã seed (`make seed`), LLM đã cấu hình trong .env. Để thử luồng sản phẩm:
`python -m scripts.seed_faq --with-demo-products`.
"""
import argparse
import asyncio
import sys
import uuid

from app.core.config import get_settings
from app.rag.factory import build_rag_engine
from app.rag.types import HistoryTurn, RAGRequest, RAGResult, RAGUser

HELP = "Lệnh: /reset  /debug  /quit"


def render(result: RAGResult, *, debug: bool, show_answer: bool = True) -> str:
    lines = []
    if show_answer:
        lines += [result.answer]
    if result.sources:
        lines += ["", "Nguồn:"] + [f"  - [{s.type.value}] {s.title} ({s.id})"
                                    + (f" -> {s.url}" if s.url else "")
                                    + (f"  điểm={s.score}" if s.score is not None else "") for s in result.sources]
    if debug:
        t = result.trace
        lines += ["", "--- debug ---",
                  f"intent: {result.intent.value}   fallback: {result.fallback_reason}",
                  f"câu hỏi độc lập: {t.standalone_question}   bộ lọc: {t.filters}",
                  "chunk: " + (", ".join(f"{r.document_id}(score={r.score:.3f}"
                                         + (f", rerank={r.rerank_score:.3f}" if r.rerank_score is not None else "")
                                         + ")" for r in t.retrieved) or "-"),
                  "bị loại (dưới ngưỡng): " + (", ".join(f"{r.document_id}(score={r.score:.3f}"
                                                         + (f", rerank={r.rerank_score:.3f}" if r.rerank_score is not None else "")
                                                         + ")" for r in t.dropped) or "-"),
                  f"tools: {t.tools_called or '-'}   model: {t.model}   prompt: {t.prompt_version}",
                  f"thời gian (ms): {t.latency_ms}   token: vào={t.usage.prompt_tokens} ra={t.usage.completion_tokens}"]
    return "\n".join(lines)


async def run(args) -> int:
    settings = get_settings()
    if args.real_clients:
        from app.integrations.order_client import OrderClient
        from app.integrations.product_client import ProductClient
        products, orders = ProductClient(), OrderClient()
    else:
        from scripts.demo_data import DemoOrderClient, DemoProductClient
        products, orders = DemoProductClient(), DemoOrderClient()
        print("(Đang dùng dữ liệu sản phẩm/đơn hàng GIẢ từ scripts/demo_data.py)")

    print("Đang nạp model (lần đầu có thể lâu)...")
    engine, close = await build_rag_engine(settings, products, orders)
    user = RAGUser(user_id="demo-user", roles=("USER",), token="demo-token") if args.login else RAGUser(user_id=None)
    print(f"Sẵn sàng. Bạn là {'người dùng đã đăng nhập' if args.login else 'khách (guest)'}. {HELP}\n")

    history: list[HistoryTurn] = []
    debug = args.debug
    try:
        while True:
            try:
                question = (await asyncio.to_thread(input, "Bạn> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not question:
                continue
            if question == "/quit":
                break
            if question == "/reset":
                history.clear()
                print("(Đã xóa lịch sử)\n")
                continue
            if question == "/debug":
                debug = not debug
                print(f"(debug = {debug})\n")
                continue

            request = RAGRequest(question, list(history[-settings.history_max_turns * 2:]), user,
                                 uuid.uuid4().hex[:8])
            if args.stream:
                print("Bot> ", end="", flush=True)
                streamed, result = [], None
                async for ev in engine.stream(request):
                    if ev.type == "token":
                        streamed.append(ev.data)
                        print(ev.data, end="", flush=True)
                    elif ev.type == "done":
                        result = ev.data
                    elif ev.type == "error":
                        print(f"\n[LỖI] {ev.data}")
                if result is None:
                    continue
                if result.answer != "".join(streamed):
                    print(f"\n(Guardrail đã thay câu trả lời) {result.answer}")
                print("\n" + render(result, debug=debug, show_answer=False))
            else:
                result = await engine.invoke(request)
                print("Bot> " + render(result, debug=debug))
            print()
            history += [HistoryTurn("user", question), HistoryTurn("assistant", result.answer)]
    finally:
        await close()
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--login", action="store_true")
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--real-clients", action="store_true")
    sys.exit(asyncio.run(run(ap.parse_args())))


if __name__ == "__main__":
    main()