"""
Chuẩn hóa văn bản tiếng Việt dùng chung cho indexing và query.

Quy tắc:
- Unicode NFC.
- Gộp khoảng trắng liên tiếp.
- Xóa khoảng trắng đầu/cuối.
- Xóa khoảng trắng thừa trước dấu câu.
- Giữ nguyên dấu tiếng Việt và chữ hoa/chữ thường.

Lưu ý:
Không loại bỏ dấu tiếng Việt vì việc này có thể làm thay đổi ý nghĩa.
"""

import re
import unicodedata


_WHITESPACE_RE = re.compile(r"\s+")
_SPACE_BEFORE_PUNCTUATION_RE = re.compile(r"\s+([,.;:!?])")


def normalize_text(text: str) -> str:
    """
    Chuẩn hóa một đoạn văn bản.

    Args:
        text: Văn bản đầu vào.

    Returns:
        Văn bản đã chuẩn hóa.

    Raises:
        TypeError: Nếu text không phải chuỗi.
    """
    if not isinstance(text, str):
        raise TypeError("text must be a string")

    # Chuẩn hóa Unicode tiếng Việt.
    text = unicodedata.normalize("NFC", text)

    # Gộp khoảng trắng và loại bỏ khoảng trắng đầu/cuối.
    text = _WHITESPACE_RE.sub(" ", text).strip()

    # Không để khoảng trắng đứng trước dấu câu.
    text = _SPACE_BEFORE_PUNCTUATION_RE.sub(r"\1", text)

    return text
