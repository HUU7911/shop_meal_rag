"""Chuẩn hóa câu hỏi + viết lại thành câu hỏi ĐỘC LẬP dựa trên lịch sử
("Còn món nào rẻ hơn?" -> "Có món cơm nào rẻ hơn Cơm gà xối mỡ không?")
và trích bộ lọc có cấu trúc (khoảng giá, danh mục, ăn chay...).

Chủ sở hữu: Member 02 (ChatService chỉ truyền history, không tự rewrite).
"""
from dataclasses import dataclass, field


@dataclass
class ProcessedQuery:
    original: str
    standalone: str
    filters: dict = field(default_factory=dict)   # {"max_price": 50000, "category": "RICE", ...}


class QueryProcessor:
    async def process(self, question: str, history: list) -> ProcessedQuery:
        raise NotImplementedError  # TODO(Member 02)
