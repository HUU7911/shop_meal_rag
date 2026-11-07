"""Làm sạch dữ liệu: bỏ HTML, chuẩn hóa Unicode NFC/khoảng trắng (dùng embedding.text_normalizer),
loại bản ghi rỗng/trùng, kiểm tra trường bắt buộc. Bản ghi lỗi -> ghi log + bỏ qua, không dừng cả job.
"""
import logging
import re
import unicodedata

from app.embedding.text_normalizer import normalize_text

log = logging.getLogger("app.ingestion.cleaner")

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    return _HTML_TAG_RE.sub(" ", text)


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return normalize_text(strip_html(text))


def clean_markdown(text: str | None) -> str:
    """Làm sạch văn bản markdown nhưng giữ lại dấu xuống dòng \n để phục vụ heading split."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", strip_html(text))
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def clean_record(record: dict) -> dict | None:
    """Kiểm tra và làm sạch bản ghi thô từ loader.
    Trả về dict đã làm sạch, hoặc None nếu không hợp lệ.
    """
    if not isinstance(record, dict):
        log.warning("Bản ghi không phải kiểu dict: %s", type(record))
        return None

    cleaned = dict(record)

    # Trường hợp 1: FAQ record
    if "question" in cleaned and "answer" in cleaned:
        q = clean_text(cleaned.get("question"))
        a = clean_text(cleaned.get("answer"))
        faq_id = str(cleaned.get("id", "")).strip()

        if not q or not a or not faq_id:
            log.warning("FAQ thiếu trường bắt buộc (id, question, answer): %s", cleaned)
            return None

        cleaned["id"] = faq_id
        cleaned["question"] = q
        cleaned["answer"] = a
        cleaned["category"] = str(cleaned.get("category") or "GENERAL").strip().upper()
        cleaned["enabled"] = bool(cleaned.get("enabled", True))

        raw_keywords = cleaned.get("keywords") or []
        if isinstance(raw_keywords, list):
            cleaned["keywords"] = [clean_text(k) for k in raw_keywords if clean_text(k)]
        else:
            cleaned["keywords"] = []

        return cleaned

    # Trường hợp 2: Policy record
    if "policy_id" in cleaned and "content" in cleaned:
        pid = str(cleaned.get("policy_id", "")).strip()
        body = clean_markdown(cleaned.get("content"))
        title = clean_text(cleaned.get("title")) or pid

        if not pid or not body:
            log.warning("Policy thiếu trường bắt buộc (policy_id, content): %s", cleaned)
            return None

        cleaned["policy_id"] = pid
        cleaned["title"] = title
        cleaned["content"] = body
        cleaned["enabled"] = bool(cleaned.get("enabled", True))
        return cleaned

    # Trường hợp 3: Product record
    if "product_id" in cleaned and "name" in cleaned:
        pid = str(cleaned.get("product_id", "")).strip()
        name = clean_text(cleaned.get("name"))
        desc = clean_text(cleaned.get("description"))

        if not pid or not name:
            log.warning("Product thiếu trường bắt buộc (product_id, name): %s", cleaned)
            return None

        cleaned["product_id"] = pid
        cleaned["name"] = name
        cleaned["description"] = desc
        cleaned["category"] = str(cleaned.get("category") or "").strip().upper()
        return cleaned

    log.warning("Không nhận diện được loại bản ghi, bỏ qua: %s", list(cleaned.keys()))
    return None
