"""Adapter LLM (LLM_PROVIDER). Timeout, retry giới hạn (tenacity), provider dự phòng,
streaming, ghi nhận token usage. Lỗi quy về GenerationError."""
from collections.abc import AsyncIterator


class LLMService:
    async def generate(self, messages: list[dict]) -> tuple[str, dict]:
        raise NotImplementedError  # TODO(Member 02)

    def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        raise NotImplementedError
