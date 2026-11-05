"""Chuẩn hóa câu hỏi + viết lại thành câu hỏi ĐỘC LẬP theo lịch sử + trích bộ lọc có cấu trúc.

Chủ sở hữu: Member 02 (ChatService chỉ truyền history, không tự rewrite).

Bộ lọc trích bằng LUẬT (rẻ, dễ test, không tốn LLM):
  max_price / min_price (VND)  : "dưới 50k", "tối đa 50.000đ", "từ 30k đến 50k", "trên 1,5tr"
  order_id                     : "đơn #123", "mã đơn 4567"
  category                     : TẮT mặc định (CATEGORY_KEYWORDS rỗng) – điền khi đã có danh mục thật
                                 từ Product Service, nếu không filter sai sẽ loại hết kết quả.
Rewrite bằng LLM chỉ chạy khi có lịch sử VÀ câu hỏi trông như câu nối tiếp ("còn món nào rẻ hơn?").
"""
import logging
import re
from dataclasses import dataclass, field

from app.embedding.text_normalizer import normalize_text
from app.rag.types import HistoryTurn
from app.rag.utils import extract_order_id, has_phrase, strip_accents

log = logging.getLogger("app.rag.query")

# {"cụm không dấu": "MÃ_DANH_MỤC"} – ví dụ {"com": "RICE", "do uong": "DRINK"}. Điền sau khi chốt danh mục.
CATEGORY_KEYWORDS: dict[str, str] = {}

_NUM = r"(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*(k|nghin|ngan|tr|trieu|d|vnd|dong)?"
_MAX = re.compile(rf"(?<!\w)(?:duoi|toi da|khong qua|nho hon|re hon|it hon|<=|<)\s*{_NUM}")
_MIN = re.compile(rf"(?<!\w)(?:tren|toi thieu|lon hon|it nhat|>=|>)\s*{_NUM}")
_RANGE = re.compile(rf"(?<!\w)tu\s*{_NUM}\s*(?:den|toi|-)\s*{_NUM}")

_FOLLOWUP_START = ("con", "vay", "the", "thi", "va", "nhung", "roi", "ma")
_FOLLOWUP_WORDS = ["do", "nay", "kia", "ay", "no", "tren", "vua roi"]

_REWRITE_SYSTEM = (
    "Bạn viết lại câu hỏi của khách hàng Shop Meal thành MỘT câu hỏi đầy đủ, độc lập, bằng tiếng Việt, "
    "dựa trên lịch sử hội thoại. Giữ nguyên ý, không trả lời câu hỏi, không thêm thông tin mới. "
    "Nếu câu hỏi đã đầy đủ thì giữ nguyên. Chỉ trả về đúng câu hỏi đã viết lại, trên một dòng."
)


@dataclass
class ProcessedQuery:
    original: str
    standalone: str
    filters: dict = field(default_factory=dict)
    rewritten: bool = False


def to_vnd(number: str, unit: str | None) -> int:
    """'50','k' -> 50000 ; '50.000','' -> 50000 ; '1,5','tr' -> 1500000 ; '50',None -> 50000 (giả định nghìn)."""
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", number):
        value = float(number.replace(".", ""))
    else:
        value = float(number.replace(",", "."))
    if unit in ("k", "nghin", "ngan"):
        value *= 1_000
    elif unit in ("tr", "trieu"):
        value *= 1_000_000
    elif unit in (None, "") and value < 1_000:
        value *= 1_000          # "dưới 50" gần như chắc chắn là 50 nghìn
    return int(round(value))


def extract_filters(question: str) -> dict:
    q = strip_accents(question)
    filters: dict = {}
    if (m := _RANGE.search(q)):
        n1, u1, n2, u2 = m.groups()
        filters["min_price"], filters["max_price"] = to_vnd(n1, u1 or u2), to_vnd(n2, u2)
    else:
        if (m := _MAX.search(q)):
            filters["max_price"] = to_vnd(*m.groups())
        if (m := _MIN.search(q)):
            filters["min_price"] = to_vnd(*m.groups())
    if (order_id := extract_order_id(question)):
        filters["order_id"] = order_id
    for phrase, code in CATEGORY_KEYWORDS.items():
        if has_phrase(q, [phrase]):
            filters["category"] = code
            break
    return filters


def looks_like_followup(question: str) -> bool:
    q = strip_accents(question)
    tokens = q.split()
    if not tokens:
        return False
    return len(tokens) <= 4 or tokens[0] in _FOLLOWUP_START or has_phrase(q, _FOLLOWUP_WORDS)


class QueryProcessor:
    def __init__(self, llm=None):
        self.llm = llm          # LLMLike; None => không rewrite (chỉ chuẩn hóa + trích bộ lọc)

    async def process(self, question: str, history: list[HistoryTurn]) -> ProcessedQuery:
        original = normalize_text(question)
        standalone, rewritten = original, False
        if self.llm is not None and history and looks_like_followup(original):
            candidate = await self._rewrite(original, history)
            if candidate and candidate != original:
                standalone, rewritten = candidate, True
        filters = extract_filters(standalone)
        for key, value in extract_filters(original).items():     # bộ lọc nói rõ ở câu gốc luôn thắng
            filters[key] = value
        return ProcessedQuery(original=original, standalone=standalone, filters=filters, rewritten=rewritten)

    async def _rewrite(self, question: str, history: list[HistoryTurn]) -> str | None:
        lines = [f"{'Khách' if t.role == 'user' else 'Trợ lý'}: {t.content[:300]}" for t in history[-4:]]
        messages = [{"role": "system", "content": _REWRITE_SYSTEM},
                    {"role": "user", "content": "Lịch sử:\n" + "\n".join(lines)
                     + f"\n\nCâu hỏi cuối của khách: {question}\nCâu hỏi độc lập:"}]
        try:
            text, _ = await self.llm.generate(messages, max_tokens=80, temperature=0.0)
        except Exception:  # noqa: BLE001 - rewrite lỗi thì dùng câu gốc, không làm hỏng lượt chat
            log.warning("Rewrite lỗi, dùng câu gốc", exc_info=True)
            return None
        first = next((ln.strip().strip('"“”') for ln in text.splitlines() if ln.strip()), "")
        first = re.sub(r"^(câu hỏi (độc lập|viết lại)\s*:\s*)", "", first, flags=re.I)
        return first if first and len(first) <= 300 else None
