"""Đọc prompt từ rag/prompts/*.md (có PROMPT_VERSION). Bọc context trong <context>...</context>
và nhắc LLM coi nội dung đó là dữ liệu, không phải chỉ dẫn."""
PROMPT_VERSION = "v1"


class PromptBuilder:
    def build(self, question: str, history: list, context: str, intent) -> list[dict]:
        raise NotImplementedError  # TODO(Member 02)
