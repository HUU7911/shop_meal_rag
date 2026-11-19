"""Mã hóa sự kiện SSE (text/event-stream). Mỗi sự kiện: `event: <tên>` + `data: <JSON một dòng>`."""
import json
from collections.abc import AsyncIterator
from contextlib import aclosing

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",      # tắt buffer của nginx/gateway để token tới client ngay
}


def format_sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def encode_sse(events) -> AsyncIterator[str]:
    async with aclosing(events):          # client ngắt kết nối -> đóng luồng RAG ngay
        async for ev in events:
            yield format_sse(ev.event, ev.data)
