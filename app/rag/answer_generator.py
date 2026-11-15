"""Tạo câu trả lời KHÔNG dùng LLM (LLM_ENABLED=false): trích nội dung có sẵn + điền dữ liệu live vào mẫu câu.

Ưu điểm: không bịa được (mọi chữ đều lấy từ KB hoặc dịch vụ), nhanh, không tốn tiền, không phụ thuộc nhà cung cấp.
Đánh đổi: câu trả lời không tự nhiên và không tổng hợp nhiều đoạn.

 * FAQ            -> trả phần "Trả lời:" của FAQ khớp nhất (+ gợi ý tối đa 2 câu hỏi liên quan).
 * Chính sách     -> trả các mục (tối đa 3) của CÙNG một tài liệu, theo thứ tự chunk.
 * Sản phẩm       -> mẫu câu từ giá/trạng thái LIVE.
 * Đơn hàng       -> mẫu câu từ dữ liệu đơn LIVE.
 * Hỏi thành phần/dị ứng -> KHÔNG BAO GIỜ khẳng định; nói chưa có thông tin và chuyển cho cửa hàng.
"""
import re
import unicodedata

from app.rag import messages
from app.rag.guardrails import _ALLERGENS, _ALLERGY_TOPIC
from app.rag.tools.common import format_price
from app.rag.types import Hit, ToolResult
from app.rag.utils import has_phrase, strip_accents
from app.schemas.chat_schema import Intent

_FAQ_ANSWER = re.compile(r"Trả lời:\s*(.*)", re.S)
_INGREDIENT_TOPIC = _ALLERGY_TOPIC + ["co chua", "khong chua", "nguyen lieu", "lam tu gi"]


def asks_ingredients(question: str) -> bool:
    """Câu hỏi về thành phần/dị ứng/dinh dưỡng (nhạy cảm: không được trả lời bằng suy đoán)."""
    lowered = unicodedata.normalize("NFC", question).lower()
    return (has_phrase(strip_accents(question), _INGREDIENT_TOPIC)
            or has_phrase(lowered, [re.escape(a) for a in _ALLERGENS]))


def _faq_answer(text: str) -> str:
    match = _FAQ_ANSWER.search(text)
    return (match.group(1) if match else text).strip()


def _section(text: str) -> str:
    """Chunk chính sách có dạng 'Tên tài liệu > Mục\\nNội dung' -> 'Mục\\nNội dung'."""
    first, _, rest = text.partition("\n")
    if ">" in first:
        heading = first.split(">", 1)[1].strip()
        return f"{heading}\n{rest.strip()}" if rest.strip() else heading
    return text.strip()


class TemplateAnswerGenerator:
    def __init__(self, support_contact: str):
        self.contact = support_contact

    def generate(self, *, intent: Intent, question: str, hits: list[Hit], tool_results: list[ToolResult]) -> str:
        if intent is Intent.ORDER_STATUS:
            return self._order(tool_results)
        if intent in (Intent.PRODUCT_SEARCH, Intent.PRODUCT_DETAIL):
            return self._product(intent, question, tool_results)
        return self._knowledge(hits)

    # ---------- FAQ / chính sách ----------
    def _knowledge(self, hits: list[Hit]) -> str:
        if not hits:
            return messages.no_info(self.contact)
        top = hits[0]
        if top.content_type == "FAQ":
            answer = _faq_answer(top.text)
            related = [h.title for h in hits[1:] if h.content_type == "FAQ" and h.document_id != top.document_id][:2]
            if related:
                answer += "\n\nBạn cũng có thể quan tâm: " + " • ".join(related)
            return answer
        same_doc = sorted((h for h in hits if h.document_id == top.document_id),
                          key=lambda h: h.payload.get("chunk_index", 0))[:3]
        return f"Theo {top.title}:\n\n" + "\n\n".join(_section(h.text) for h in same_doc)

    # ---------- sản phẩm ----------
    def _product(self, intent: Intent, question: str, tool_results: list[ToolResult]) -> str:
        items = [t.data for t in tool_results if t.ok and t.found and t.data]
        if not items:
            return messages.no_info(self.contact)
        if asks_ingredients(question):
            desc = (f" Mô tả hiện có: {items[0]['description']}"
                    if intent is Intent.PRODUCT_DETAIL and items[0].get("description") else "")
            return ("Mình chưa có thông tin chi tiết về thành phần hoặc chất gây dị ứng của món này." + desc
                    + f"\nĐể chắc chắn, bạn vui lòng hỏi trực tiếp {self.contact} nhé.")
        if intent is Intent.PRODUCT_DETAIL:
            d = items[0]
            text = f"{d['name']} có giá {format_price(d['price'])} và {d['status_phrase']}."
            return f"{text} {d['description']}".strip() if d.get("description") else text
        lines = [f"- {d['name']} — {format_price(d['price'])} ({d['status_phrase']})" for d in items]
        return f"Mình tìm được {len(items)} món phù hợp:\n" + "\n".join(lines)

    # ---------- đơn hàng ----------
    def _order(self, tool_results: list[ToolResult]) -> str:
        blocks = []
        for t in tool_results:
            if not (t.ok and t.found and t.data):
                continue
            d = t.data
            line = (f"Đơn #{d['order_id']} {d['status_phrase']}. Tổng tiền {format_price(d['total'])}, "
                    f"đặt lúc {d['created_at']}.")
            if d["items"]:
                line += " Gồm: " + ", ".join(f"{i.get('name', '?')} x{i.get('quantity', 1)}" for i in d["items"]) + "."
            blocks.append(line)
        return "\n".join(blocks) if blocks else messages.no_info(self.contact)