"""EmbeddingService DÙNG CHUNG cho rag (query) và ingestion (document).

Đảm bảo cùng model + cùng cách chuẩn hóa. Nếu model dùng prefix cho query/passage
(ví dụ e5: "query: " / "passage: ") thì xử lý ở đây, không để nơi khác tự xử lý.

Lưu ý hiệu năng: encode là CPU-bound -> gọi qua `run_in_threadpool` từ code async.
"""
from dataclasses import dataclass


@dataclass
class EncodedText:
    dense: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


class EmbeddingService:
    model_name: str
    dim: int

    def __init__(self, model_name: str, dim: int, device: str = "cpu"):
        raise NotImplementedError  # TODO(Member 02): nạp model một lần (lifespan)

    def embed_query(self, text: str) -> EncodedText:
        raise NotImplementedError

    def embed_documents(self, texts: list[str]) -> list[EncodedText]:
        raise NotImplementedError
