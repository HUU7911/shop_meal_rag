"""Phân loại ý định: FAQ_POLICY | PRODUCT_SEARCH | PRODUCT_DETAIL | ORDER_STATUS | SMALLTALK | OUT_OF_SCOPE.

Gợi ý: bắt đầu bằng luật + từ khóa (rẻ, dễ debug), sau đó cân nhắc LLM nhỏ/classifier.
Đo độ chính xác routing trong eval (eval/golden_set.jsonl có trường expected_intent).
"""
from app.schemas.chat_schema import Intent


class IntentRouter:
    def route(self, standalone_question: str) -> Intent:
        raise NotImplementedError  # TODO(Member 02)
