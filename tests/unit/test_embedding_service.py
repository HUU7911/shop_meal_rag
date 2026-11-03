
import numpy as np
import pytest

from app.embedding.embedding_service import EmbeddingService, EncodedText


def test_encoded_text_structure():
    result = EncodedText(
        dense=[0.1, 0.2],
        sparse_indices=[1, 2],
        sparse_values=[0.5, 0.8],
    )

    assert len(result.dense) == 2
    assert len(result.sparse_indices) == len(result.sparse_values)


def test_invalid_model_name():
    with pytest.raises(ValueError):
        EmbeddingService(
            model_name="unknown-model",
            dim=1024,
        )


def test_invalid_dimension():
    with pytest.raises(ValueError):
        EmbeddingService(
            model_name="BAAI/bge-m3",
            dim=0,
        )


def test_empty_documents():
    # Không cần khởi tạo model để kiểm tra danh sách rỗng.
    service = EmbeddingService.__new__(EmbeddingService)
    service.provider = "bge-m3"

    assert service.embed_documents([]) == []


def test_validate_text():
    assert EmbeddingService._validate_text(
        "  Cơm   gà  "
    ) == "Cơm gà"


def test_reject_empty_text():
    with pytest.raises(ValueError):
        EmbeddingService._validate_text("   ")


def test_reject_non_string():
    with pytest.raises(TypeError):
        EmbeddingService._validate_text(None)


def test_e5_prefix_and_output(monkeypatch):
    service = EmbeddingService.__new__(EmbeddingService)
    service.provider = "e5"
    service.dim = 3
    service.batch_size = 2
    service.device = "cpu"

    class FakeModel:
        def encode(self, inputs, **kwargs):
            assert inputs == ["query: Cơm gà"]

            assert kwargs["normalize_embeddings"] is True

            return np.array([[0.1, 0.2, 0.3]])

    service._model = FakeModel()

    result = service.embed_query("Cơm gà")

    assert len(result.dense) == 3
    assert result.sparse_indices == []
    assert result.sparse_values == []


def test_e5_document_prefix():
    service = EmbeddingService.__new__(EmbeddingService)
    service.provider = "e5"
    service.dim = 3
    service.batch_size = 2
    service.device = "cpu"

    class FakeModel:
        def encode(self, inputs, **kwargs):
            assert inputs == ["passage: Cơm gà"]
            return np.array([[0.1, 0.2, 0.3]])

    service._model = FakeModel()

    result = service.embed_documents(["Cơm gà"])

    assert len(result) == 1
    assert len(result[0].dense) == 3
