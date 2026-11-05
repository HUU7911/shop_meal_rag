"""Tool tìm sản phẩm. Hai đường, đều trả GIÁ/TRẠNG THÁI LIVE:

 1. Có `product_ids` (từ truy xuất ngữ nghĩa trên mô tả): lấy live từng sản phẩm, lọc theo giá THẬT.
 2. Không có kết quả ở (1) (hoặc câu hỏi dạng liệt kê/lọc giá): ProductClient.search(category, max_price)
    có phân trang -> trả tối đa `size` món.
Sản phẩm hết hàng/ẩn vẫn được trả (kèm trạng thái) để LLM nói đúng thực tế.
"""
import asyncio
import logging

from app.rag.tools.common import UNAVAILABLE_NOTE, render_product
from app.rag.types import ToolResult
from app.schemas.chat_schema import SourceType

log = logging.getLogger("app.rag.tools")


def _in_price_range(info, filters: dict) -> bool:
    if (hi := filters.get("max_price")) is not None and info.price > hi:
        return False
    if (lo := filters.get("min_price")) is not None and info.price < lo:
        return False
    return True


def _to_result(info) -> ToolResult:
    return ToolResult("product_search", SourceType.PRODUCT, info.product_id, info.name,
                      render_product(info), url=info.url)


async def product_search(client, *, product_ids: list[str], filters: dict, size: int = 5) -> list[ToolResult]:
    results: list[ToolResult] = []
    failed = False
    if product_ids:
        infos = await asyncio.gather(*(client.get(pid) for pid in product_ids[:size]), return_exceptions=True)
        for pid, info in zip(product_ids, infos):
            if isinstance(info, Exception):
                log.warning("product_search: get(%s) lỗi: %s", pid, info)
                failed = True
            elif info is not None and _in_price_range(info, filters):
                results.append(_to_result(info))
    if not results:
        try:
            items, _total = await client.search(category=filters.get("category"),
                                                max_price=filters.get("max_price"), page=1, size=size)
            results = [_to_result(i) for i in items if _in_price_range(i, filters)]
        except Exception:  # noqa: BLE001
            log.warning("product_search: search lỗi", exc_info=True)
            failed = True
    if not results and failed:
        return [ToolResult("product_search", SourceType.PRODUCT, "-", "-", UNAVAILABLE_NOTE,
                           ok=False, found=False)]
    return results
