"""Chuẩn hóa câu hỏi + viết lại thành câu hỏi ĐỘC LẬP theo lịch sử + trích bộ lọc có cấu trúc.

Chủ sở hữu: Member 02 (ChatService chỉ truyền history, không tự rewrite).

Bộ lọc trích bằng LUẬT (rẻ, dễ test, không tốn LLM):
  max_price / min_price (VND)  : "dưới 50k" (=49.999, loại mốc), "tối đa 50.000đ" (=50.000), "từ 30k đến 50k", "trên 1,5tr"
                                 – giá trị luôn là cận ĐÃ BAO GỒM mốc, nên so sánh bằng <= / >=
  order_id                     : "đơn #123", "mã đơn 4567"
  category                     : TẮT mặc định (CATEGORY_KEYWORDS rỗng) – điền khi đã có danh mục thật
                                 từ Product Service, nếu không filter sai sẽ loại hết kết quả.
Rewrite bằng LLM chỉ chạy khi có lịch sử VÀ câu hỏi trông như câu nối tiếp ("còn món nào rẻ hơn?").
Không có LLM: câu có dấu hiệu nối tiếp rõ ràng được NỐI vào sau câu hỏi trước của khách (chỉ nhớ 1 lượt gần nhất).
"""
import logging
import re
from dataclasses import dataclass, field

from app.embedding.text_normalizer import normalize_text
from app.rag.types import HistoryTurn
from app.rag.intent_router import GREETING, OFF_TOPIC
from app.rag.utils import extract_order_id, has_phrase, strip_accents

log = logging.getLogger("app.rag.query")

# {"cụm không dấu": "MÃ_DANH_MỤC"} – ví dụ {"com": "RICE", "do uong": "DRINK"}. Điền sau khi chốt danh mục.
CATEGORY_KEYWORDS: dict[str, str] = {}

_NUM = r"(\d{1,3}(?:\.\d{3})+|\d+(?:[.,]\d+)?)\s*(k|nghin|ngan|tr|trieu|d|vnd|dong)?"
_MAX = re.compile(rf"(?<!\w)(duoi|toi da|khong qua|nho hon|re hon|it hon|<=|<)\s*{_NUM}")
_MIN = re.compile(rf"(?<!\w)(tren|toi thieu|lon hon|it nhat|>=|>)\s*{_NUM}")
# "dưới/rẻ hơn/trên/lớn hơn" là so sánh CHẶT (loại mốc); "tối đa/tối thiểu/không quá/ít nhất" thì gồm mốc.
_STRICT = {"duoi", "nho hon", "re hon", "it hon", "<", "tren", "lon hon", ">"}
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
    carried_over: str | None = None     # câu hỏi trước được NỐI vào (chỉ chế độ không LLM)


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
            kw, number, unit = m.groups()
            filters["max_price"] = to_vnd(number, unit) - (1 if kw in _STRICT else 0)
        if (m := _MIN.search(q)):
            kw, number, unit = m.groups()
            filters["min_price"] = to_vnd(number, unit) + (1 if kw in _STRICT else 0)
    if (order_id := extract_order_id(question)):
        filters["order_id"] = order_id
    for phrase, code in CATEGORY_KEYWORDS.items():
        if has_phrase(q, [phrase]):
            filters["category"] = code
            break
    return filters

_PRICE_COMPARATORS = {("duoi",), ("tren",), ("toi", "da"), ("toi", "thieu"), ("khong", "qua"), ("nho", "hon"),
                      ("lon", "hon"), ("re", "hon"), ("it", "hon"), ("it", "nhat"), ("tu",), ("den",), ("khoang",)}
_PRICE_UNITS = {"nghin", "ngan", "k", "tr", "trieu", "d", "dong", "vnd"}
_NUMBER_TOKEN = re.compile(r"^\d[\d.,]*(?:k|tr|d|vnd|nghin|ngan|trieu)?$")
# Từ đệm KHÔNG thể là một phần tên món/danh mục. Các từ mơ hồ (tôi/tỏi, bao/bánh bao, la/lá lốt, nha/cơm nhà, gia/gia vị,
# không/"không cay", còn/het) KHÔNG nằm ở đây mà chỉ bị bỏ khi VỊ TRÍ cho thấy là từ đệm (xem _is_filler):
# bỏ nhầm một chữ của tên món làm hỏng truy xuất, còn giữ lại một từ đệm chỉ làm điểm rerank giảm nhẹ.
_FILLER = {"co", "nao", "gi", "cho", "minh", "xem", "muon", "shop", "giup", "nhe", "oi", "duoc", "hang", "tien",
           "voi"}


def _is_filler(plain: list[str], i: int) -> bool:
    token, nxt = plain[i], plain[i + 1] if i + 1 < len(plain) else None
    if token in _FILLER:
        return True
    return ((token == "khong" and nxt is None)                          # "...không?" cuối câu, khác "món không cay"
            or (token == "gia" and (nxt is None or nxt in {"bao", "nhieu", "tien", "nao"}      # khác "gia vị"
                                    or ("bao", "nhieu") in zip(plain, plain[1:])))             # "giá trà đào bao nhiêu"
            or (token == "bao" and nxt == "nhieu")                      # khác "bánh bao"
            or (token == "nhieu" and i > 0 and plain[i - 1] == "bao")
            or (token in {"con", "het"} and nxt == "hang")              # "còn/hết hàng"
            or (token == "tim" and i == 0))                             # "tìm ..." đầu câu, khác "tim heo"


def semantic_query(question: str) -> str:
    """Phần NỘI DUNG của câu hỏi sản phẩm: bỏ điều kiện giá, từ hỏi tồn kho và từ đệm.

    "Có trà đào nào dưới 50 nghìn không?" -> "trà đào". Không còn gì sau khi bỏ -> trả câu gốc.
    Vì sao: cross-encoder chấm câu có điều kiện giá rất thấp dù món đúng (đo thực tế: câu trên 0.024, còn "trà đào"
    0.989) nên món đúng bị loại ở ngưỡng. Giá/tồn kho không cần cho truy xuất: product_search lọc theo giá THẬT và lấy
    trạng thái live. Ưu tiên giữ chữ khi không chắc để không làm mất từ trong tên món (tỏi, bánh bao, lá lốt...).
    """
    original = question.split()
    plain = [strip_accents(t.lower()).strip("?!.,;:()\"'") for t in original]
    drop: set[int] = set()
    for i in range(len(plain)):
        for comparator in _PRICE_COMPARATORS:
            n = len(comparator)
            if tuple(plain[i:i + n]) == comparator and i + n < len(plain) and _NUMBER_TOKEN.match(plain[i + n]):
                drop.update(range(i, i + n + 1))
                if i + n + 1 < len(plain) and plain[i + n + 1] in _PRICE_UNITS:
                    drop.add(i + n + 1)
    for i, token in enumerate(plain):
        if _NUMBER_TOKEN.match(token) or _is_filler(plain, i) or (token in _PRICE_UNITS and i - 1 in drop):
            drop.add(i)
    kept = [o for i, o in enumerate(original) if i not in drop]
    return " ".join(kept).strip("?!.,; ") or question

def looks_like_followup(question: str) -> bool:
    q = strip_accents(question)
    tokens = q.split()
    if not tokens:
        return False
    return len(tokens) <= 4 or tokens[0] in _FOLLOWUP_START or has_phrase(q, _FOLLOWUP_WORDS)


_TEMPORAL_BEFORE_NAY = {"hom", "ngay", "nam", "tuan", "thang", "buoi"}   # "hôm nay", "tuần này"... là thời gian, KHÔNG phải đại từ


def has_followup_cue(question: str) -> bool:
    """Dấu hiệu RÕ RÀNG của câu nối tiếp (bắt đầu bằng 'còn/vậy/thế...' hoặc có 'đó/này/kia/ấy'). Chặt hơn
    `looks_like_followup` (không tính độ dài) vì bản không-LLM sẽ NỐI câu trước vào, nối nhầm sẽ làm lạc đề.
    Không dấu thì 'này' và 'nay' giống nhau, nên 'nay' chỉ tính khi KHÔNG đứng sau hôm/ngày/năm/tuần/tháng."""
    tokens = re.findall(r"\w+", strip_accents(question))
    if not tokens:
        return False
    if tokens[0] in _FOLLOWUP_START:
        return True
    for i, token in enumerate(tokens):
        if token in ("do", "kia", "ay"):
            return True
        if token == "nay" and (i == 0 or tokens[i - 1] not in _TEMPORAL_BEFORE_NAY):
            return True
    return False


class QueryProcessor:
    def __init__(self, llm=None):
        self.llm = llm          # LLMLike; None => không rewrite (chỉ chuẩn hóa + trích bộ lọc)

    async def process(self, question: str, history: list[HistoryTurn]) -> ProcessedQuery:
        original = normalize_text(question)
        standalone, rewritten, carried_over = original, False, None
        if self.llm is not None and history and looks_like_followup(original):
            candidate = await self._rewrite(original, history)
            if candidate and candidate != original:
                standalone, rewritten = candidate, True
        elif self.llm is None and history and has_followup_cue(original) \
                and not has_phrase(strip_accents(original), GREETING + OFF_TOPIC):   # chào hỏi/lạc đề: không nối ngữ cảnh cũ
            # Không có LLM: dùng luật — nối câu hỏi gần nhất của khách vào đầu để truy xuất/định tuyến có ngữ cảnh.
            previous = next((t.content for t in reversed(history) if t.role == "user"), "")
            if previous:
                standalone, rewritten = f"{previous[:300].rstrip()} {original}", True
                carried_over = previous[:120].strip()
        filters = extract_filters(standalone)
        for key, value in extract_filters(original).items():     # bộ lọc nói rõ ở câu gốc luôn thắng
            filters[key] = value
        return ProcessedQuery(original=original, standalone=standalone, filters=filters, rewritten=rewritten,
                              carried_over=carried_over)

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