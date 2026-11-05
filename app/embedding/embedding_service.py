"""EmbeddingService DÙNG CHUNG cho rag (query) và ingestion (document).

Hai backend, chọn theo tên model:
  * "bge-m3"  -> FlagEmbedding.BGEM3FlagModel: dense + sparse trong 1 lần encode (hybrid).
  * khác      -> sentence-transformers: chỉ dense (sparse rỗng => retriever tự dùng dense-only).
                 Model họ e5 tự thêm tiền tố "query: " / "passage: " tại đây.

Hiệu năng: encode là CPU-bound -> code async PHẢI gọi qua asyncio.to_thread (Retriever đã làm).
Lưu ý: API của FlagEmbedding thay đổi giữa các version; nếu khởi tạo lỗi hãy đối chiếu tài liệu version đã cài.
"""
import logging
from dataclasses import dataclass, field

from app.core.errors import ConfigurationError, EmbeddingError
from app.embedding.text_normalizer import normalize_text

log = logging.getLogger("app.embedding")


@dataclass
class EncodedText:
    dense: list[float]
    sparse_indices: list[int] = field(default_factory=list)
    sparse_values: list[float] = field(default_factory=list)

    @property
    def has_sparse(self) -> bool:
        return bool(self.sparse_indices)


class EmbeddingService:
    def __init__(self, model_name: str, dim: int, device: str = "cpu", batch_size: int = 16,
                 max_length: int = 512):
        self.model_name, self.dim, self.device = model_name, dim, device
        self.batch_size, self.max_length = batch_size, max_length
        lowered = model_name.lower()
        self._is_bge_m3 = "bge-m3" in lowered
        self._is_e5 = "e5" in lowered
        self._model = self._load()
        self._check_dim()

    # ---------- khởi tạo ----------
    def _load(self):
        try:
            if self._is_bge_m3:
                from FlagEmbedding import BGEM3FlagModel
                use_fp16 = self.device != "cpu"
                for kwargs in ({"devices": [self.device]}, {"device": self.device}, {}):
                    try:
                        return BGEM3FlagModel(self.model_name, use_fp16=use_fp16, **kwargs)
                    except TypeError:       # khác chữ ký giữa các version
                        continue
                raise EmbeddingError("Không khởi tạo được BGEM3FlagModel (kiểm tra version FlagEmbedding)")
            from sentence_transformers import SentenceTransformer
            return SentenceTransformer(self.model_name, device=self.device)
        except EmbeddingError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"Không nạp được embedding model '{self.model_name}': {exc}") from exc

    def _check_dim(self) -> None:
        probe = self.embed_query("kiểm tra kích thước vector")
        if len(probe.dense) != self.dim:
            raise ConfigurationError(
                f"EMBEDDING_DIM={self.dim} nhưng model '{self.model_name}' trả vector {len(probe.dense)} chiều")

    @property
    def supports_sparse(self) -> bool:
        return self._is_bge_m3

    # ---------- API ----------
    def embed_query(self, text: str) -> EncodedText:
        return self._encode([self._prefix(text, "query: ")])[0]

    def embed_documents(self, texts: list[str]) -> list[EncodedText]:
        if not texts:
            return []
        return self._encode([self._prefix(t, "passage: ") for t in texts])

    # ---------- nội bộ ----------
    def _prefix(self, text: str, prefix: str) -> str:
        text = normalize_text(text)
        return prefix + text if self._is_e5 else text

    def _encode(self, texts: list[str]) -> list[EncodedText]:
        try:
            if self._is_bge_m3:
                out = self._model.encode(texts, batch_size=self.batch_size, max_length=self.max_length,
                                         return_dense=True, return_sparse=True, return_colbert_vecs=False)
                result = []
                for dense, weights in zip(out["dense_vecs"], out["lexical_weights"]):
                    items = sorted((int(k), float(v)) for k, v in weights.items())
                    result.append(EncodedText(
                        dense=[float(x) for x in dense],
                        sparse_indices=[k for k, _ in items],
                        sparse_values=[v for _, v in items]))
                return result
            vectors = self._model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True)
            return [EncodedText(dense=[float(x) for x in v]) for v in vectors]
        except Exception as exc:  # noqa: BLE001
            raise EmbeddingError(f"Lỗi khi encode: {exc}") from exc
