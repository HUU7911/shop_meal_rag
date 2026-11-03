"""Ghép chunk + kết quả tool thành context trong giới hạn token, khử trùng lặp,
gắn nhãn nguồn [1], [2]... và tạo danh sách SourceItem (có url deep link)."""


class ContextBuilder:
    def build(self, chunks: list[dict], tool_results: list[dict], max_tokens: int):
        raise NotImplementedError  # TODO(Member 02)
