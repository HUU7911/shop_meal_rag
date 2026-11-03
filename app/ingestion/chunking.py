"""Chiến lược chunk THEO LOẠI dữ liệu (chốt ở đây, đo lại bằng eval):

FAQ     : 1 Q&A = 1 chunk, KHÔNG cắt. Text embed = câu hỏi + keywords (+ câu trả lời ngắn).
POLICY  : cắt theo heading (MarkdownHeaderTextSplitter), gắn đường dẫn heading vào đầu chunk
          ("Chính sách hủy đơn > Điều kiện hủy: ..."); chunk dài mới cắt tiếp (~400-600 token, overlap ~10%).
PRODUCT : 1 sản phẩm = 1 chunk: tên + danh mục + mô tả + thành phần. KHÔNG đưa giá/trạng thái vào text.
DOCUMENT: cắt theo heading/đoạn như POLICY.
"""
from app.ingestion.payload import ChunkPayload


def chunk_faq(item: dict) -> list[ChunkPayload]:
    raise NotImplementedError  # TODO(Member 03)


def chunk_policy(markdown: str, meta: dict) -> list[ChunkPayload]:
    raise NotImplementedError


def chunk_product(product: dict) -> list[ChunkPayload]:
    raise NotImplementedError
