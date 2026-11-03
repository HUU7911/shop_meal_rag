"""Cross-encoder rerank (RERANK_MODEL). Chạy trong threadpool. Cắt còn RERANK_TOP_N."""


class Reranker:
    def rerank(self, question: str, candidates: list[dict], top_n: int) -> list[dict]:
        raise NotImplementedError  # TODO(Member 02)
