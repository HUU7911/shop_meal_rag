"""Client Product Service – nguồn DUY NHẤT gọi Product Service (dùng cho rag.tools và ingestion).

GIẢ ĐỊNH VỀ API (Product Service chưa chốt - xem docs/CONTRACTS.md §5; sửa ở hằng số dưới đây hoặc
truyền vào constructor khi đã chốt, phần còn lại của hệ thống không bị ảnh hưởng):
  GET {PRODUCT_SERVICE_URL}/api/v1/product/products/{id}
  GET {PRODUCT_SERVICE_URL}/api/v1/product/products?keyword=&category=&maxPrice=&page=&size=
      -> Spring Page {"content":[...],"totalElements":N}  hoặc  {"items":[...],"total":N}  hoặc  [...]
      (`page` của Spring bắt đầu từ 0; client nhận page bắt đầu từ 1 và tự đổi)
Phần ánh xạ trường chấp nhận cả snake_case (product_id) lẫn camelCase (productId).
"""
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.core.errors import UpstreamUnavailableError
from app.integrations.http import ServiceHttpClient

PRODUCTS_PATH = "/api/v1/product/products"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")     # chặn path traversal / ký tự lạ trong URL
_MAX_ITER_PAGES = 500                                 # chặn vòng lặp vô hạn khi upstream lỗi phân trang


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


def _first(raw: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if raw.get(k) is not None:
            return raw[k]
    return default


def _name_of(value: Any) -> str:
    if isinstance(value, dict):
        return str(_first(value, "name", "title", default=""))
    return "" if value is None else str(value)


def parse_product(raw: dict[str, Any]) -> ProductInfo | None:
    """Trả None nếu bản ghi thiếu id (bỏ qua thay vì làm hỏng cả danh sách)."""
    pid = _first(raw, "product_id", "productId", "id")
    if pid is None:
        return None
    pid = str(pid)
    status = _first(raw, "status")
    if status is None:                                  # một số API chỉ có cờ available
        avail = _first(raw, "available", "isAvailable")
        status = "AVAILABLE" if avail in (True, "true", 1) else "OUT_OF_STOCK" if avail is not None else "UNKNOWN"
    try:
        price = float(_first(raw, "price", default=0) or 0)
    except (TypeError, ValueError):
        price = 0.0
    return ProductInfo(
        product_id=pid,
        name=str(_first(raw, "name", "title", default="")),
        description=str(_first(raw, "description", default="") or ""),
        category=_name_of(_first(raw, "category", "categoryName")),
        product_type=_name_of(_first(raw, "product_type", "productType", "type")),
        price=price,
        status=str(status).upper(),
        url=_first(raw, "url") or f"/products/{pid}",
    )


def _unwrap_page(data: Any) -> tuple[list[dict], int]:
    """Chuẩn hóa nhiều dạng trả về của danh sách -> (items, total)."""
    if isinstance(data, list):
        return data, len(data)
    if isinstance(data, dict):
        # Bọc kiểu {"data": {...}} hoặc {"result": {...}}
        for wrap in ("data", "result"):
            if isinstance(data.get(wrap), (dict, list)):
                return _unwrap_page(data[wrap])
        items = _first(data, "content", "items", "products", default=[])
        total = _first(data, "totalElements", "total", "totalItems", default=len(items))
        return list(items), int(total)
    return [], 0


class ProductClient:
    """Timeout = SERVICE_HTTP_TIMEOUT_SECONDS; lỗi -> UpstreamUnavailableError."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float | None = None,
        max_retries: int = 2,
        products_path: str = PRODUCTS_PATH,
        transport: httpx.AsyncBaseTransport | None = None,
        http: ServiceHttpClient | None = None,
    ):
        settings = get_settings()
        self.products_path = products_path.rstrip("/")
        self._http = http or ServiceHttpClient(
            base_url or settings.product_service_url,
            timeout=timeout if timeout is not None else settings.service_http_timeout_seconds,
            max_retries=max_retries,
            transport=transport,
            name="Product Service",
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get(self, product_id: str) -> ProductInfo | None:
        if not _SAFE_ID.match(str(product_id)):
            return None
        data = await self._http.get_json(f"{self.products_path}/{quote(str(product_id), safe='')}")
        if isinstance(data, dict):
            for wrap in ("data", "result"):
                if isinstance(data.get(wrap), dict):
                    data = data[wrap]
                    break
        return parse_product(data) if isinstance(data, dict) else None

    async def search(self, *, keyword: str | None = None, category: str | None = None,
                     max_price: float | None = None, page: int = 1, size: int = 10
                     ) -> tuple[list[ProductInfo], int]:
        """Trả (items, total). `page` bắt đầu từ 1."""
        data = await self._http.get_json(
            self.products_path,
            params={"keyword": keyword, "category": category, "maxPrice": max_price,
                    "page": max(page, 1) - 1, "size": size},
        )
        if data is None:
            return [], 0
        raw_items, total = _unwrap_page(data)
        items = [p for p in (parse_product(r) for r in raw_items if isinstance(r, dict)) if p]
        return items, total

    async def iter_all(self, page_size: int = 100) -> AsyncIterator[ProductInfo]:
        """Dùng cho ingestion: duyệt toàn bộ sản phẩm (từng trang, không nạp hết vào RAM)."""
        seen = 0
        for page in range(1, _MAX_ITER_PAGES + 1):
            items, total = await self.search(page=page, size=page_size)
            for item in items:
                yield item
            seen += len(items)
            if not items or seen >= total or len(items) < page_size:
                return
        raise UpstreamUnavailableError("Product Service phân trang bất thường (quá nhiều trang).")
