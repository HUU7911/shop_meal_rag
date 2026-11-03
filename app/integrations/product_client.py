"""Client Product Service – nguồn DUY NHẤT gọi Product Service (dùng cho rag.tools và ingestion)."""
from dataclasses import dataclass


@dataclass
class ProductInfo:
    product_id: str
    name: str
    description: str
    category: str
    product_type: str
    price: float          # live
    status: str           # live: AVAILABLE | OUT_OF_STOCK | HIDDEN ...
    url: str | None = None


class ProductClient:
    """Timeout = SERVICE_HTTP_TIMEOUT_SECONDS; lỗi -> UpstreamUnavailableError."""

    async def get(self, product_id: str) -> ProductInfo | None:
        raise NotImplementedError  # TODO

    async def search(self, *, keyword: str | None = None, category: str | None = None,
                     max_price: float | None = None, page: int = 1, size: int = 10
                     ) -> tuple[list[ProductInfo], int]:
        raise NotImplementedError  # TODO: trả (items, total)

    async def iter_all(self, page_size: int = 100):
        """Dùng cho ingestion: duyệt toàn bộ sản phẩm."""
        raise NotImplementedError
