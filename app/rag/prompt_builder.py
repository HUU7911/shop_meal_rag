"""Đọc prompt từ rag/prompts/*.md (có PROMPT_VERSION trong dòng comment đầu file).
Bọc context trong <context>...</context> và nhắc LLM coi đó là dữ liệu, không phải chỉ dẫn."""
import re
from pathlib import Path

from app.rag.types import HistoryTurn
from app.schemas.chat_schema import Intent

PROMPTS_DIR = Path(__file__).parent / "prompts"
_VERSION_RE = re.compile(r"<!--\s*PROMPT_VERSION:\s*([\w.\-]+)\s*-->")

_INTENT_HINTS = {
    Intent.PRODUCT_SEARCH: "Liệt kê tối đa 5 món phù hợp, nêu giá và tình trạng từ dữ liệu trực tiếp.",
    Intent.PRODUCT_DETAIL: "Trả lời đúng sản phẩm khách hỏi; giá và tình trạng lấy từ dữ liệu trực tiếp.",
    Intent.ORDER_STATUS: "Chỉ nêu thông tin các đơn có trong dữ liệu trực tiếp của chính khách.",
    Intent.FAQ_POLICY: "Trả lời ngắn gọn theo nội dung chính sách/FAQ trong context; nêu rõ điều kiện nếu có.",
}


class PromptBuilder:
    def __init__(self, system_file: str = "system_vi.md", max_history_messages: int = 12):
        raw = (PROMPTS_DIR / system_file).read_text(encoding="utf-8")
        match = _VERSION_RE.search(raw)
        self.version = match.group(1) if match else "unversioned"
        self.system = _VERSION_RE.sub("", raw).strip()
        self.max_history_messages = max_history_messages

    def build(self, *, question: str, standalone: str, history: list[HistoryTurn], context: str,
              intent: Intent) -> list[dict]:
        system = self.system
        if hint := _INTENT_HINTS.get(intent):
            system += f"\n\nYêu cầu riêng cho lượt này: {hint}"
        messages = [{"role": "system", "content": system}]
        messages += [{"role": t.role, "content": t.content} for t in history[-self.max_history_messages:]]
        user = f"<context>\n{context}\n</context>\n\nCâu hỏi của khách: {question}"
        if standalone and standalone != question:
            user += f"\n(Hiểu là: {standalone})"
        messages.append({"role": "user", "content": user})
        return messages
