"""Chiến lược chunk THEO LOẠI dữ liệu (chốt ở đây, đo lại bằng eval):

FAQ     : 1 Q&A = 1 chunk, KHÔNG cắt. Text embed = câu hỏi + keywords (+ câu trả lời ngắn).
POLICY  : cắt theo heading (MarkdownHeaderTextSplitter), gắn đường dẫn heading vào đầu chunk
          ("Chính sách hủy đơn > Điều kiện hủy: ..."); chunk dài mới cắt tiếp (~400-600 token, overlap ~10%).
PRODUCT : 1 sản phẩm = 1 chunk: tên + danh mục + mô tả + thành phần. KHÔNG đưa giá/trạng thái vào text.
DOCUMENT: cắt theo heading/đoạn như POLICY.
"""
import re

from app.ingestion.payload import ChunkPayload, ContentType, content_hash, now_iso, point_id


def chunk_faq(item: dict) -> list[ChunkPayload]:
    """1 Q&A = 1 chunk, không cắt. Text embed = câu hỏi + keywords."""
    faq_id = str(item["id"])
    question = item["question"]
    answer = item["answer"]
    keywords = item.get("keywords") or []

    text = f"Câu hỏi: {question}\nTrả lời: {answer}"
    embed_text = f"{question} {' '.join(keywords)}".strip()

    payload = ChunkPayload(
        chunk_id=point_id(ContentType.FAQ, faq_id, 0),
        document_id=faq_id,
        content_type="FAQ",
        title=question,
        text=text,
        chunk_index=0,
        content_hash=content_hash(text),
        updated_at=now_iso(),
        enabled=item.get("enabled", True),
        category=item.get("category"),
        embed_text=embed_text,
    )
    return [payload]


def chunk_policy(markdown: str, meta: dict) -> list[ChunkPayload]:
    """Cắt policy theo heading và gán đường dẫn heading vào đầu chunk."""
    policy_id = str(meta.get("policy_id", "policy"))
    title = str(meta.get("title", policy_id))
    version = str(meta.get("version", "1.0"))
    effective_date = meta.get("effective_date")
    if effective_date and "T" not in str(effective_date):
        effective_date = f"{effective_date}T00:00:00Z"

    enabled = meta.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.lower() == "true"

    # Tách theo heading ##
    sections = [s.strip() for s in re.split(r"(?m)^##\s+", markdown) if s.strip()]
    chunks: list[ChunkPayload] = []

    # Bỏ qua phần mở đầu nếu là tiêu đề # chính
    subsections = sections[1:] if len(sections) > 1 and sections[0].startswith("#") else sections

    for i, sec in enumerate(subsections):
        heading, _, content = sec.partition("\n")
        heading = heading.strip()
        content = content.strip()
        text = f"{title} > {heading}\n{content}"

        payload = ChunkPayload(
            chunk_id=point_id(ContentType.POLICY, policy_id, i),
            document_id=policy_id,
            content_type="POLICY",
            title=title,
            text=text,
            chunk_index=i,
            content_hash=content_hash(text),
            updated_at=now_iso(),
            enabled=enabled,
            version=version,
            effective_date=effective_date,
            embed_text=text,
        )
        chunks.append(payload)

    return chunks


def chunk_product(product: dict) -> list[ChunkPayload]:
    """1 sản phẩm = 1 chunk: tên + danh mục + mô tả.
    QUY TẮC: Giá và trạng thái chỉ lưu snapshot để lọc thô, KHÔNG đưa vào text embed.
    """
    pid = str(product["product_id"])
    name = str(product["name"])
    category = str(product.get("category") or "")
    desc = str(product.get("description") or "")
    ptype = str(product.get("product_type") or "FOOD")

    # Text chỉ gồm tên, danh mục, mô tả (không chứa giá/status)
    text = f"{name} (Danh mục: {category}). {desc}".strip()

    price = float(product["price"]) if "price" in product and product["price"] is not None else None
    status = str(product.get("status") or "AVAILABLE")

    payload = ChunkPayload(
        chunk_id=point_id(ContentType.PRODUCT, pid, 0),
        document_id=pid,
        content_type="PRODUCT",
        title=name,
        text=text,
        chunk_index=0,
        content_hash=content_hash(text),
        updated_at=now_iso(),
        enabled=product.get("enabled", True),
        category=category,
        product_id=pid,
        product_type=ptype,
        status_snapshot=status,
        price_snapshot=price,
        source_url=product.get("url"),
        embed_text=text,
    )
    return [payload]
