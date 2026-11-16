"""Kiểm tra chất lượng KB đang nằm trong Qdrant và sinh golden set từ chính FAQ. Hàm thuần: nhận [(point_id, payload)].

Dùng qua `python -m scripts.audit_kb`. Mục đích: bắt lỗi ở RANH GIỚI ingestion -> retrieval (thiếu trường bắt buộc, nội dung giữ chỗ,
trùng câu hỏi...) TRƯỚC khi đổ lỗi cho retriever/reranker.
"""
from collections import Counter

from app.rag.utils import lacks_diacritics, strip_accents

# Trường bắt buộc theo docs/CONTRACTS.md §3 (Retriever sẽ lỗi nếu thiếu document_id)
REQUIRED_FIELDS = ("chunk_id", "document_id", "content_type", "title", "text", "chunk_index", "content_hash",
                   "updated_at", "enabled")
PLACEHOLDER_MARKERS = ("[mẫu]", "thay bằng nội dung", "lorem ipsum", "todo", "tbd")
MIN_TEXT_CHARS = 40


def audit_payloads(items: list[tuple], *, expected_model: str | None = None) -> dict:
    meta = [p for _, p in items if p.get("content_type") == "META"]
    content = [(i, p) for i, p in items if p.get("content_type") != "META"]
    missing = {}
    for pid, p in content:
        absent = [f for f in REQUIRED_FIELDS if f not in p or p[f] in (None, "")]
        if absent:
            missing[str(pid)] = absent
    dup_chunks = sorted(f"{d}#{c}" for (d, c), n in Counter((p.get("document_id"), p.get("chunk_index"))
                                                             for _, p in content).items() if n > 1)
    lengths = sorted(len(str(p.get("text", ""))) for _, p in content)
    short = sorted(str(p.get("document_id")) for _, p in content if len(str(p.get("text", ""))) < MIN_TEXT_CHARS)
    placeholders = sorted(str(p.get("document_id")) for _, p in content
                          if any(m in str(p.get("text", "")).lower() for m in PLACEHOLDER_MARKERS))
    faq_titles = Counter(strip_accents(str(p.get("title", ""))) for _, p in content if p.get("content_type") == "FAQ")
    meta_model = meta[0].get("embedding_model") if meta else None

    issues, warnings = [], []
    if missing:
        issues.append(f"{len(missing)} chunk thiếu trường bắt buộc (vd. {next(iter(missing.items()))})")
    if dup_chunks:
        issues.append(f"{len(dup_chunks)} cặp (document_id, chunk_index) bị trùng: {dup_chunks[:5]}")
    if not meta:
        warnings.append("Không có điểm META: Retriever.verify() chỉ kiểm tra được số chiều vector, không kiểm tra được tên model")
    elif expected_model and meta_model != expected_model:
        issues.append(f"KB build bằng '{meta_model}' nhưng cấu hình đang dùng '{expected_model}'")
    if placeholders:
        warnings.append(f"{len(placeholders)} chunk còn nội dung giữ chỗ: {placeholders[:5]}")
    if short:
        warnings.append(f"{len(short)} chunk quá ngắn (< {MIN_TEXT_CHARS} ký tự): {short[:5]}")
    if any(c > 1 for c in faq_titles.values()):
        warnings.append(f"Câu hỏi FAQ trùng nhau (nhãn mơ hồ): {sorted(t for t, c in faq_titles.items() if c > 1)[:5]}")
    return {
        "total_points": len(items), "content_chunks": len(content), "meta_point": bool(meta),
        "by_content_type": dict(Counter(p.get("content_type", "?") for _, p in content)),
        "disabled_chunks": sum(1 for _, p in content if p.get("enabled") is False),
        "text_chars": {"min": lengths[0], "median": lengths[len(lengths) // 2], "max": lengths[-1]} if lengths else {},
        "issues": issues, "warnings": warnings,
    }


def build_golden_rows(items: list[tuple], *, start: int = 1) -> list[dict]:
    """Mỗi FAQ -> câu hỏi gốc + bản KHÔNG DẤU. CHỈ dùng với `eval --mode retrieval`.
    Thiên lệch cần biết: câu gốc chính là tiêu đề của chunk nên gần như luôn tìm đúng (kiểm tra ingestion, không đo khả năng
    hiểu cách diễn đạt khác). Muốn đo diễn đạt khác, hãy tự viết thêm câu hỏi của khách thật."""
    faq = [(i, p) for i, p in items if p.get("content_type") == "FAQ" and p.get("enabled", True) is not False
           and p.get("title")]
    titles = Counter(strip_accents(p["title"]) for _, p in faq)
    rows, n = [], start
    for _, p in sorted(faq, key=lambda x: str(x[1].get("document_id"))):
        title = p["title"].strip()
        if titles[strip_accents(title)] > 1:           # hai FAQ cùng câu hỏi: không biết chunk nào là "đúng"
            continue
        variants = [("auto-title", title)]
        if not lacks_diacritics(title):
            variants.append(("auto-unaccented", strip_accents(title)))
        for source, question in variants:
            rows.append({"id": f"kb{n:03d}", "question": question, "expected_intent": "FAQ_POLICY",
                         "expected_doc_ids": [str(p["document_id"])], "expected_answer_points": [], "history": [],
                         "source": source})
            n += 1
    return rows