"""Guardrails đầu vào/đầu ra. Quy tắc đầy đủ: docs/SECURITY.md.

Đầu vào : độ dài, prompt injection thô, che PII trước khi log.
Đầu ra  : yêu cầu có nguồn; không có context -> fallback + handoff; giá/trạng thái chỉ từ tool live;
          dị ứng/dinh dưỡng chỉ nêu khi có dữ liệu, kèm lưu ý kiểm tra lại với cửa hàng.
"""


class Guardrails:
    def check_input(self, question: str) -> None:
        raise NotImplementedError  # TODO(Member 02) – raise GuardrailBlocked nếu vi phạm

    def check_output(self, answer: str, *, has_context: bool) -> str:
        raise NotImplementedError
