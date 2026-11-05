"""Tool tra đơn hàng của CHÍNH user qua OrderClient + JWT của user.

Bảo mật: chỉ dùng token của user (Order Service là nơi kiểm tra sở hữu). Guest KHÔNG bao giờ tới đây
(RAGEngine chặn trước bằng LOGIN_REQUIRED). Không dùng service account để tra đơn người khác.
"""
import logging

from app.rag.tools.common import UNAVAILABLE_NOTE, format_price, status_label
from app.rag.types import ToolResult
from app.schemas.chat_schema import SourceType

log = logging.getLogger("app.rag.tools")


def _render(order) -> str:
    items = ", ".join(f"{i.get('name', '?')} x{i.get('quantity', 1)}" for i in (order.items or []))
    return (f"Đơn #{order.order_id}: trạng thái {status_label(order.status)}, tổng {format_price(order.total)}, "
            f"đặt lúc {order.created_at}" + (f"; gồm: {items}" if items else "") + " (dữ liệu trực tiếp).")


async def order_status(client, order_id: str | None, *, user_token: str | None) -> list[ToolResult]:
    if not user_token:
        raise PermissionError("order_status cần token của người dùng")
    try:
        if order_id:
            order = await client.get_order(order_id, user_token=user_token)
            orders = [order] if order else []
        else:
            orders = await client.list_recent(user_token=user_token, limit=3)
    except Exception:  # noqa: BLE001
        log.warning("order_status lỗi", exc_info=True)
        return [ToolResult("order_status", SourceType.ORDER, order_id or "-", "-", UNAVAILABLE_NOTE,
                           ok=False, found=False)]
    if not orders:
        text = (f"Không tìm thấy đơn #{order_id} thuộc tài khoản của bạn." if order_id
                else "Tài khoản của bạn chưa có đơn hàng gần đây.")
        return [ToolResult("order_status", SourceType.ORDER, order_id or "-", "Đơn hàng", text, found=False)]
    return [ToolResult("order_status", SourceType.ORDER, o.order_id, f"Đơn #{o.order_id}", _render(o))
            for o in orders]
