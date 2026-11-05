"""Tiện ích dùng chung trong rag: bỏ dấu, ước lượng token, đo thời gian, trích mã đơn."""
import re
import time
import unicodedata
from contextlib import contextmanager

from app.rag.types import RAGTrace


def strip_accents(text: str) -> str:
    """Chữ thường, bỏ dấu tiếng Việt (đ -> d). Dùng để SO KHỚP luật, không dùng để embed."""
    text = unicodedata.normalize("NFC", text).lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def has_phrase(stripped_text: str, phrases: list[str] | tuple[str, ...]) -> bool:
    """True nếu có cụm nào xuất hiện như TỪ NGUYÊN VẸN (tránh 'gia' khớp 'giao').
    Các cụm là regex (đã ở dạng không dấu, chữ thường)."""
    return any(re.search(rf"(?<!\w)(?:{p})(?!\w)", stripped_text) for p in phrases)


def estimate_tokens(text: str) -> int:
    """Ước lượng thô cho tiếng Việt (~3 ký tự/token). Đủ cho ngân sách context; không dùng để tính tiền."""
    return max(1, len(text) // 3)


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    max_chars = max_tokens * 3
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + "…"


def snippet(text: str, n: int = 160) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


@contextmanager
def timed(trace: RAGTrace, name: str):
    """Cộng dồn thời gian (ms) của một bước vào trace.latency_ms[name]."""
    start = time.perf_counter()
    try:
        yield
    finally:
        trace.latency_ms[name] = trace.latency_ms.get(name, 0) + int((time.perf_counter() - start) * 1000)


# Mã đơn dạng số (>= 3 chữ số). TODO: đổi nếu Order Service dùng mã chữ-số.
_ORDER_ID = re.compile(r"(?:#|(?<!\w)ma don\b\s*|(?<!\w)don hang\b\s*|(?<!\w)don\b\s*)#?(\d{3,})")


def extract_order_id(text: str) -> str | None:
    m = _ORDER_ID.search(strip_accents(text))
    return m.group(1) if m else None
