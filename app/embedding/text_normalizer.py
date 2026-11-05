"""Chuẩn hóa tiếng Việt dùng chung cho cả index và query:
Unicode NFC, gộp khoảng trắng, chuẩn hóa dấu câu. KHÔNG bỏ dấu tiếng Việt khỏi text gốc
(có thể thêm biến thể không dấu cho sparse/keyword nếu eval cho thấy cần)."""
import re
import unicodedata

_WS = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    return _WS.sub(" ", text).strip()