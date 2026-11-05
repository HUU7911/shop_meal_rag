"""Guardrails đầu vào/đầu ra. Quy tắc đầy đủ: docs/SECURITY.md.

Đầu vào : giới hạn độ dài + prompt injection thô -> raise GuardrailBlocked.
Đầu ra  : không lộ system prompt; không khẳng định "không chứa <chất gây dị ứng>" khi context không có;
          luôn kèm lưu ý khi nói về dị ứng/thành phần/dinh dưỡng.
Ngoài ra: mask_pii() để che SĐT/email/số dài trước khi ghi log.
"""
import re
import unicodedata
from dataclasses import dataclass

from app.core.errors import GuardrailBlocked
from app.rag import messages
from app.rag.utils import has_phrase, strip_accents

_INJECTION = [
    r"bo qua (?:moi |tat ca |cac )?(?:huong dan|chi dan|quy tac|chi thi)",
    r"quen (?:het |moi )?(?:huong dan|chi dan|quy tac)",
    r"(?:in|hien thi|tiet lo|cho toi xem|doc) (?:ra )?(?:system prompt|prompt he thong|chi dan he thong|huong dan he thong)",
    r"system prompt", r"prompt he thong",
    r"ignore (?:all |any |the )?(?:previous |above |prior )?(?:instructions|rules)",
    r"(?:reveal|show|print) (?:your |the )?(?:system )?prompt",
    r"you are now", r"developer mode", r"jailbreak",
    r"dong vai .{0,40}(?:khong (?:co )?gioi han|khong bi rang buoc)",
]
_LEAK_MARKERS = ("quy tắc bắt buộc", "prompt_version", "<context>", "</context>")
# Có dấu có chủ đích: "cua" (cua) khác "của", "sữa" khác "sửa". Câu trả lời của LLM thường có dấu.
_ALLERGENS = ["gluten", "đậu phộng", "đậu nành", "lạc", "sữa", "trứng", "hải sản", "tôm", "cua", "hạt"]
_ALLERGY_TOPIC = ["di ung", "thanh phan", "dinh duong", "calo", "kcal", "gluten", "chat bao quan"]
_NEGATIVE_CLAIM = re.compile(
    r"không (?:chứa|có|dùng|sử dụng|bao gồm)\s+(?:(?!thông tin)\w+\s+){0,2}?(" + "|".join(_ALLERGENS) + r")(?!\w)")

_PII = [(re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "***@***"), (re.compile(r"(?<!\d)\d{9,16}(?!\d)"), "***")]


def mask_pii(text: str) -> str:
    for pattern, repl in _PII:
        text = pattern.sub(repl, text)
    return text


@dataclass
class OutputCheck:
    answer: str
    fallback_reason: str | None = None      # "UNSAFE_OUTPUT" khi đã thay câu trả lời


class Guardrails:
    def __init__(self, *, max_length: int = 1000, support_contact: str = "bộ phận chăm sóc khách hàng"):
        self.max_length, self.support_contact = max_length, support_contact

    def check_input(self, question: str) -> str:
        question = question.strip()
        if not question:
            raise GuardrailBlocked("Câu hỏi trống")
        if len(question) > self.max_length:
            raise GuardrailBlocked("Câu hỏi quá dài")
        if has_phrase(strip_accents(question), _INJECTION):
            raise GuardrailBlocked("Phát hiện yêu cầu thao túng chỉ dẫn hệ thống")
        return question

    def check_output(self, answer: str, *, context_text: str = "", question: str = "") -> OutputCheck:
        answer = answer.strip()
        lowered = answer.lower()
        if not answer or any(marker in lowered for marker in _LEAK_MARKERS):
            return OutputCheck(messages.unsafe_output(self.support_contact), "UNSAFE_OUTPUT")

        context_lower = unicodedata.normalize("NFC", context_text).lower()
        answer_lower = unicodedata.normalize("NFC", answer).lower()
        for match in _NEGATIVE_CLAIM.finditer(answer_lower):
            if not has_phrase(context_lower, [re.escape(match.group(1))]):
                return OutputCheck(messages.unsafe_output(self.support_contact), "UNSAFE_OUTPUT")

        mentions_allergen = has_phrase(answer_lower, [re.escape(a) for a in _ALLERGENS])
        topic = has_phrase(strip_accents(question) + " " + strip_accents(answer), _ALLERGY_TOPIC)
        if (topic or mentions_allergen) and messages.ALLERGY_NOTE not in answer:
            answer = f"{answer}\n\n{messages.ALLERGY_NOTE}"
        return OutputCheck(answer)
