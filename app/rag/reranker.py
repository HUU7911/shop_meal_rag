"""Cross-encoder rerank (RERANK_MODEL). Sync + CPU-bound: engine gọi qua asyncio.to_thread.

Điểm: CrossEncoder.predict với model 1 nhãn thường áp sigmoid -> 0..1 (HÃY in thử phân bố điểm
trên vài câu đúng/sai trước khi đặt ngưỡng; nếu model trả logit thì đổi ngưỡng cho phù hợp).
"""
import logging

from app.core.errors import ConfigurationError
from app.rag.types import Hit

log = logging.getLogger("app.rag.reranker")


class Reranker:
    def __init__(self, model_name: str, *, enabled: bool = True, device: str = "cpu", max_length: int = 512):
        self.enabled = enabled
        self._model = None
        if enabled:
            try:
                from sentence_transformers import CrossEncoder
                self._model = CrossEncoder(model_name, device=device, max_length=max_length)
            except Exception as exc:  # noqa: BLE001
                raise ConfigurationError(f"Không nạp được reranker '{model_name}': {exc}") from exc

    def rerank(self, question: str, hits: list[Hit], top_n: int) -> list[Hit]:
        if not self.enabled or self._model is None or not hits:
            return hits[:top_n]
        pairs = [(question, f"{h.title}\n{h.text}") for h in hits]
        scores = self._model.predict(pairs)
        for hit, score in zip(hits, scores):
            hit.rerank_score = float(score)
        return sorted(hits, key=lambda h: h.rerank_score or 0.0, reverse=True)[:top_n]
