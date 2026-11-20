"""Client sản phẩm đọc từ FILE JSON (vd. data/products/food.json) — cùng giao diện với `ProductClient`.

Dùng khi Product Service thật chưa sẵn sàng: giá/trạng thái lấy từ file mỗi lần hỏi (nạp một lần lúc khởi động,
sửa file thì khởi động lại). Khi Member 01 làm xong ProductClient thật, chỉ cần thay đối tượng này — các tool,
ingestion và engine không phải đổi gì.

Quy ước:
  * `search()` KHÔNG trả sản phẩm HIDDEN (không được lộ món đã ẩn khi liệt kê) và xếp món còn hàng lên trước.
  * `get()` trả cả món HIDDEN/OUT_OF_STOCK để bot nói đúng thực tế ("tạm ngừng bán"/"hết hàng").
  * So khớp danh mục/từ khóa không phân biệt hoa thường và dấu tiếng Việt.
"""
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.errors import ConfigurationError
from app.integrations.product_client import ProductInfo
from app.rag.utils import strip_accents

log = logging.getLogger("app.integrations.json_product")

_REQUIRED = ("product_id", "name", "price")


def _norm(text: str | None) -> str:
    return " ".join(strip_accents(str(text or "")).lower().split())


def load_products(path: Path | str) -> list[ProductInfo]:
    """Đọc và kiểm tra file; lỗi dữ liệu báo rõ bản ghi nào (không im lặng bỏ qua)."""
    file = Path(path)
    if not file.exists():
        raise ConfigurationError(f"Không thấy file sản phẩm: {file}")
    try:
        raw = json.loads(file.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ConfigurationError(f"File sản phẩm không phải JSON hợp lệ ({file}): {exc}") from exc
    if not isinstance(raw, list):
        raise ConfigurationError(f"File sản phẩm phải là một danh sách JSON ({file})")
    products: list[ProductInfo] = []
    seen: set[str] = set()
    for n, item in enumerate(raw, 1):
        if not isinstance(item, dict) or any(item.get(k) in (None, "") for k in _REQUIRED):
            raise ConfigurationError(f"{file.name}: mục #{n} thiếu một trong các trường {_REQUIRED}")
        pid = str(item["product_id"]).strip()
        if pid in seen:
            raise ConfigurationError(f"{file.name}: product_id '{pid}' bị trùng (mục #{n})")
        seen.add(pid)
        try:
            price = float(item["price"])
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(f"{file.name}: giá không hợp lệ ở '{pid}': {item['price']!r}") from exc
        products.append(ProductInfo(
            product_id=pid, name=str(item["name"]).strip(), description=str(item.get("description") or ""),
            category=str(item.get("category") or ""), product_type=str(item.get("product_type") or ""),
            price=price, status=str(item.get("status") or "AVAILABLE").upper(), url=item.get("url")))
    log.info("Đã nạp %d sản phẩm từ %s", len(products), file)
    return products


class JsonProductClient:
    def __init__(self, path: Path | str = "data/products/food.json"):
        self.path = Path(path)
        self._items = load_products(self.path)
        self._by_id = {p.product_id: p for p in self._items}

    async def get(self, product_id: str) -> ProductInfo | None:
        return self._by_id.get(str(product_id))

    async def search(self, *, keyword: str | None = None, category: str | None = None,
                     max_price: float | None = None, page: int = 1, size: int = 10
                     ) -> tuple[list[ProductInfo], int]:
        cat, kw = _norm(category), _norm(keyword)
        items = [p for p in self._items
                 if p.status != "HIDDEN"
                 and (not cat or _norm(p.category) == cat)
                 and (max_price is None or p.price <= max_price)
                 and (not kw or kw in _norm(f"{p.name} {p.description}"))]
        items.sort(key=lambda p: p.status != "AVAILABLE")          # sort ổn định: giữ thứ tự file trong từng nhóm
        start = (max(page, 1) - 1) * size
        return items[start:start + size], len(items)

    async def iter_all(self, page_size: int = 100) -> AsyncIterator[ProductInfo]:
        for product in self._items:
            yield product