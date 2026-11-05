"""Tool chi tiết 1 sản phẩm (giá, còn hàng) qua ProductClient.get – luôn LIVE."""
import logging

from app.rag.tools.common import UNAVAILABLE_NOTE, render_product
from app.rag.types import ToolResult
from app.schemas.chat_schema import SourceType

log = logging.getLogger("app.rag.tools")


async def product_detail(client, product_id: str) -> ToolResult:
    try:
        info = await client.get(product_id)
    except Exception:  # noqa: BLE001 - lỗi tool không được làm hỏng cả lượt chat
        log.warning("product_detail(%s) lỗi", product_id, exc_info=True)
        return ToolResult("product_detail", SourceType.PRODUCT, product_id, product_id,
                          UNAVAILABLE_NOTE, ok=False, found=False)
    if info is None:
        return ToolResult("product_detail", SourceType.PRODUCT, product_id, product_id,
                          f"Không tìm thấy sản phẩm {product_id}.", found=False)
    return ToolResult("product_detail", SourceType.PRODUCT, info.product_id, info.name,
                      render_product(info), url=info.url)
