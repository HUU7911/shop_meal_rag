"""Tool tìm sản phẩm: dùng ProductClient.search (+ hybrid retriever cho mô tả).
Trả danh sách có phân trang với GIÁ/TRẠNG THÁI LIVE. Dùng cho câu hỏi liệt kê & lọc giá."""


async def product_search(filters: dict, page: int = 1, size: int = 10) -> dict:
    raise NotImplementedError  # TODO(Member 02)
