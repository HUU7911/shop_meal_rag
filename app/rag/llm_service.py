"""Adapter LLM theo chuẩn OpenAI-compatible (`POST {LLM_BASE_URL}/chat/completions`).

Dùng được với OpenAI và các máy chủ tương thích (vLLM, Ollama, OpenRouter, Azure qua gateway...).
Nếu dùng API không tương thích (vd. Anthropic native) hãy thêm adapter cùng giao diện `LLMLike`.

 * Timeout = LLM_TIMEOUT_SECONDS; retry (tenacity) CHỈ cho lỗi tạm thời: timeout/kết nối/429/5xx.
 * Hết retry -> thử 1 lần model dự phòng (LLM_FALLBACK_MODEL, cùng endpoint) nếu có cấu hình.
 * Mọi lỗi cuối cùng quy về GenerationError.
 * Dùng `max_tokens` (một số model OpenAI mới cần `max_completion_tokens` — đổi tại _payload nếu gặp).
"""
import json
import logging
from collections.abc import AsyncIterator

import httpx
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.errors import ConfigurationError, GenerationError
from app.rag.protocols import LLMChunk

log = logging.getLogger("app.rag.llm")
DEFAULT_BASE_URL = "https://api.openai.com/v1"


class _Transient(Exception):
    pass


class LLMService:
    def __init__(self, settings, client: httpx.AsyncClient | None = None):
        if not settings.llm_model:
            raise ConfigurationError("LLM_MODEL chưa được cấu hình")
        self.model_name = settings.llm_model
        self.fallback_model = settings.llm_fallback_model or None
        self.base_url = (settings.llm_base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = settings.llm_api_key.get_secret_value()
        self.default_max_tokens = settings.llm_max_output_tokens
        self.max_retries = settings.llm_max_retries
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(settings.llm_timeout_seconds))
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ---------- chung ----------
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"} if self.api_key \
            else {"Content-Type": "application/json"}

    def _payload(self, model: str, messages: list[dict], max_tokens: int | None, temperature: float,
                 stream: bool) -> dict:
        body = {"model": model, "messages": messages, "temperature": temperature,
                "max_tokens": max_tokens or self.default_max_tokens, "stream": stream}
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        if response.status_code == 429 or response.status_code >= 500:
            raise _Transient(f"HTTP {response.status_code}")
        if response.status_code >= 400:
            raise GenerationError(f"LLM trả lỗi HTTP {response.status_code}")

    # ---------- không stream ----------
    async def _call_once(self, model: str, messages, max_tokens, temperature) -> tuple[str, dict]:
        try:
            response = await self._client.post(f"{self.base_url}/chat/completions", headers=self._headers(),
                                               json=self._payload(model, messages, max_tokens, temperature, False))
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise _Transient(str(exc)) from exc
        self._check_status(response)
        try:
            data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise GenerationError("Phản hồi LLM không đúng định dạng") from exc
        usage = data.get("usage") or {}
        return text, {"prompt_tokens": usage.get("prompt_tokens", 0),
                      "completion_tokens": usage.get("completion_tokens", 0)}

    async def _with_retry(self, model: str, messages, max_tokens, temperature) -> tuple[str, dict]:
        async for attempt in AsyncRetrying(stop=stop_after_attempt(self.max_retries + 1),
                                           wait=wait_exponential(multiplier=0.5, max=4),
                                           retry=retry_if_exception_type(_Transient), reraise=True):
            with attempt:
                return await self._call_once(model, messages, max_tokens, temperature)
        raise GenerationError("unreachable")  # pragma: no cover

    async def generate(self, messages: list[dict], *, max_tokens: int | None = None,
                       temperature: float = 0.2) -> tuple[str, dict]:
        try:
            return await self._with_retry(self.model_name, messages, max_tokens, temperature)
        except (_Transient, GenerationError) as primary:
            if not self.fallback_model:
                raise GenerationError(f"LLM không khả dụng: {primary}") from primary
            log.warning("LLM chính lỗi (%s) -> dùng model dự phòng %s", primary, self.fallback_model)
            try:
                return await self._call_once(self.fallback_model, messages, max_tokens, temperature)
            except (_Transient, GenerationError) as exc:
                raise GenerationError(f"LLM và dự phòng đều lỗi: {exc}") from exc

    # ---------- stream ----------
    async def _stream_model(self, model: str, messages, max_tokens, temperature) -> AsyncIterator[LLMChunk]:
        try:
            async with self._client.stream("POST", f"{self.base_url}/chat/completions", headers=self._headers(),
                                           json=self._payload(model, messages, max_tokens, temperature, True)) as r:
                if r.status_code >= 400:
                    await r.aread()
                self._check_status(r)
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        return
                    try:
                        event = json.loads(raw)
                    except ValueError:
                        continue
                    if event.get("usage"):
                        u = event["usage"]
                        yield LLMChunk(usage={"prompt_tokens": u.get("prompt_tokens", 0),
                                              "completion_tokens": u.get("completion_tokens", 0)})
                    choices = event.get("choices") or []
                    if choices and (piece := (choices[0].get("delta") or {}).get("content")):
                        yield LLMChunk(text=piece)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise _Transient(str(exc)) from exc

    async def stream(self, messages: list[dict], *, max_tokens: int | None = None,
                     temperature: float = 0.2) -> AsyncIterator[LLMChunk]:
        """Lỗi TRƯỚC token đầu tiên -> thử model dự phòng; lỗi GIỮA CHỪNG -> GenerationError (engine phát `error`)."""
        started = False
        models = [self.model_name] + ([self.fallback_model] if self.fallback_model else [])
        last: Exception | None = None
        for model in models:
            try:
                async for chunk in self._stream_model(model, messages, max_tokens, temperature):
                    started = started or bool(chunk.text)
                    yield chunk
                return
            except (_Transient, GenerationError) as exc:
                last = exc
                if started:
                    break
                log.warning("Stream lỗi với %s: %s", model, exc)
        raise GenerationError(f"LLM stream lỗi: {last}")
