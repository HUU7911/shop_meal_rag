"""Chuẩn hóa tiếng Việt dùng chung cho query và document."""

import re
import unicodedata

_WS = re.compile(r"\s+")
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([,.!?;:%])")


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        raise TypeError("Text phải là chuỗi.")

    text = unicodedata.normalize("NFC", text)
    text = _WS.sub(" ", text).strip()
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)

    return text
