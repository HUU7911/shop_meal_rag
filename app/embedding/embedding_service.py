
"""
EmbeddingService dùng chung cho RAG query và ingestion document.

Models:
- BAAI/bge-m3:
    Dense vector + sparse lexical weights.
- intfloat/multilingual-e5-large:
    Dense vector; sparse vector để rỗng.

Không khởi tạo model ở cấp module. Tạo một instance trong application lifespan
và dùng chung cho ingestion và RAG.
"""

from dataclasses import dataclass
import math

from app.embedding.text_normalizer import normalize_text


@dataclass
class EncodedText:
    dense: list[float]
    sparse_indices: list[int]
    sparse_values: list[float]


class EmbeddingService:
    """Tạo embedding nhất quán cho query và document."""

    BGE_M3 = "BAAI/bge-m3"
    E5_LARGE = "intfloat/multilingual-e5-large"

    def __init__(
        self,
        model_name: str,
        dim: int,
        device: str = "cpu",
        batch_size: int = 8,
        max_length: int = 512,
    ):
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must be a non-empty string")

        if dim <= 0:
            raise ValueError("dim must be greater than zero")

        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")

        if max_length <= 0:
            raise ValueError("max_length must be greater than zero")

        self.model_name = model_name.strip()
        self.dim = dim
        self.device = device
        self.batch_size = batch_size
        self.max_length = max_length

        normalized_name = self.model_name.lower()

        if normalized_name == self.BGE_M3.lower():
            self.provider = "bge-m3"
            self._init_bge_m3()

        elif normalized_name == self.E5_LARGE.lower():
            self.provider = "e5"
            self._init_e5()

        else:
            raise ValueError(
                f"Unsupported embedding model: {self.model_name}. "
                f"Supported models: {self.BGE_M3}, {self.E5_LARGE}"
            )

    def _validate_device(self) -> None:
        """Kiểm tra CUDA nếu người dùng yêu cầu chạy GPU."""
        if self.device.startswith("cuda"):
            import torch

            if not torch.cuda.is_available():
                raise RuntimeError(
                    f"CUDA device '{self.device}' was requested, "
                    "but CUDA is not available."
                )

    def _init_bge_m3(self) -> None:
        """Khởi tạo BGE-M3 với dense và sparse output."""
        self._validate_device()

        from FlagEmbedding import BGEM3FlagModel

        self._model = BGEM3FlagModel(
            self.model_name,
            use_fp16=self.device.startswith("cuda"),
            devices=self.device,
            batch_size=self.batch_size,
            query_max_length=self.max_length,
            passage_max_length=self.max_length,
            return_dense=True,
            return_sparse=True,
        )

        self._tokenizer = self._model.tokenizer

    def _init_e5(self) -> None:
        """Khởi tạo Multilingual E5."""
        self._validate_device()

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            self.model_name,
            device=self.device,
        )
        self._tokenizer = None

    @staticmethod
    def _validate_text(text: str) -> str:
        if not isinstance(text, str):
            raise TypeError("Input text must be a string")

        normalized = normalize_text(text)

        if not normalized:
            raise ValueError("Input text must not be empty")

        return normalized

    def _normalize_texts(self, texts: list[str]) -> list[str]:
        if not isinstance(texts, list):
            raise TypeError("texts must be a list of strings")

        return [self._validate_text(text) for text in texts]

    def _encode_bge(
        self,
        texts: list[str],
    ) -> list[EncodedText]:
        """Encode BGE-M3 và chuyển lexical weights thành sparse vectors."""
        output = self._model.encode(
            texts,
            batch_size=self.batch_size,
            max_length=self.max_length,
            return_dense=True,
            return_sparse=True,
            return_colbert_vecs=False,
        )

        dense_vectors = output["dense_vecs"]
        lexical_weights = output["lexical_weights"]

        if len(dense_vectors) != len(texts):
            raise RuntimeError("BGE-M3 returned an invalid dense vector count")

        if len(lexical_weights) != len(texts):
            raise RuntimeError("BGE-M3 returned an invalid sparse vector count")

        results: list[EncodedText] = []

        for dense_vector, token_weights in zip(
            dense_vectors,
            lexical_weights,
        ):
            dense = [float(value) for value in dense_vector.tolist()]

            if len(dense) != self.dim:
                raise ValueError(
                    f"Expected dense dimension {self.dim}, "
                    f"received {len(dense)}"
                )

            # BGE-M3 trả token -> weight.
            # Qdrant sparse vector cần integer index -> weight.
            sparse_map: dict[int, float] = {}

            for token_id, weight in token_weights.items():
                # BGE-M3 lexical_weights sử dụng token ID dạng string,
                # không phải token text.
                try:
                    token_id = int(token_id)
                    weight = float(weight)
                except (TypeError, ValueError):
                    continue

                if token_id < 0:
                    continue

                if not math.isfinite(weight) or weight <= 0:
                    continue

                sparse_map[token_id] = (
                        sparse_map.get(token_id, 0.0) + weight
                )

            sparse_indices = sorted(sparse_map)
            sparse_values = [
                float(sparse_map[index])
                for index in sparse_indices
            ]

            results.append(
                EncodedText(
                    dense=dense,
                    sparse_indices=sparse_indices,
                    sparse_values=sparse_values,
                )
            )

        return results

    def _encode_e5(
        self,
        texts: list[str],
        is_query: bool,
    ) -> list[EncodedText]:
        """Encode E5 với prefix đúng cho query và passage."""
        if is_query:
            inputs = [f"query: {text}" for text in texts]
        else:
            inputs = [f"passage: {text}" for text in texts]

        vectors = self._model.encode(
            inputs,
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
            device=self.device,
        )

        if len(vectors) != len(texts):
            raise RuntimeError("E5 returned an invalid vector count")

        results: list[EncodedText] = []

        for vector in vectors:
            dense = [float(value) for value in vector.tolist()]

            if len(dense) != self.dim:
                raise ValueError(
                    f"Expected dense dimension {self.dim}, "
                    f"received {len(dense)}"
                )

            results.append(
                EncodedText(
                    dense=dense,
                    sparse_indices=[],
                    sparse_values=[],
                )
            )

        return results

    def embed_query(self, text: str) -> EncodedText:
        """Embedding cho câu hỏi người dùng."""
        normalized = self._validate_text(text)

        if self.provider == "bge-m3":
            return self._encode_bge([normalized])[0]

        return self._encode_e5([normalized], is_query=True)[0]

    def embed_documents(self, texts: list[str]) -> list[EncodedText]:
        """Embedding cho danh sách document/chunk."""
        normalized_texts = self._normalize_texts(texts)

        if not normalized_texts:
            return []

        if self.provider == "bge-m3":
            return self._encode_bge(normalized_texts)

        return self._encode_e5(
            normalized_texts,
            is_query=False,
        )
