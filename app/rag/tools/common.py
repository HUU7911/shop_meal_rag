"""Định dạng dữ liệu LIVE thành văn bản cho LLM. Giá/trạng thái chỉ đến từ đây, không từ chunk."""
STATUS_LABELS = {
    "AVAILABLE": "Còn hàng", "IN_STOCK": "Còn hàng", "ACTIVE": "Còn hàng",
    "OUT_OF_STOCK": "Hết hàng", "SOLD_OUT": "Hết hàng",
    "HIDDEN": "Tạm ngừng bán", "INACTIVE": "Tạm ngừng bán", "DISABLED": "Tạm ngừng bán",
}
UNAVAILABLE_NOTE = "Không kiểm tra được giá/tình trạng trực tiếp lúc này."


def format_price(value: float) -> str:
    return f"{int(round(value)):,}".replace(",", ".") + "đ"


def status_label(status: str) -> str:
    return STATUS_LABELS.get(str(status).upper(), str(status))


def render_product(info) -> str:
    return (f"{info.name} — giá {format_price(info.price)} — {status_label(info.status)} "
            f"(dữ liệu trực tiếp). Mô tả: {info.description}".strip())


PRODUCT_STATUS_PHRASES = {
    "AVAILABLE": "đang còn hàng", "IN_STOCK": "đang còn hàng", "ACTIVE": "đang còn hàng",
    "OUT_OF_STOCK": "hiện đã hết hàng", "SOLD_OUT": "hiện đã hết hàng",
    "HIDDEN": "tạm ngừng bán", "INACTIVE": "tạm ngừng bán", "DISABLED": "tạm ngừng bán",
}
# Mã trạng thái đơn do Order Service quyết định; mã lạ sẽ được hiển thị nguyên văn.
ORDER_STATUS_PHRASES = {
    "PENDING": "đang chờ xác nhận", "CONFIRMED": "đã được xác nhận", "PREPARING": "đang được chế biến",
    "DELIVERING": "đang được giao", "SHIPPING": "đang được giao", "DELIVERED": "đã giao thành công",
    "COMPLETED": "đã hoàn thành", "CANCELLED": "đã bị hủy", "CANCELED": "đã bị hủy",
}


def product_status_phrase(status: str) -> str:
    return PRODUCT_STATUS_PHRASES.get(str(status).upper(), f"có trạng thái {status}")


def order_status_phrase(status: str) -> str:
    return ORDER_STATUS_PHRASES.get(str(status).upper(), f"có trạng thái {status}")


def product_data(info) -> dict:
    return {"name": info.name, "price": info.price, "status": info.status,
            "status_phrase": product_status_phrase(info.status), "description": info.description, "url": info.url}


def order_data(order) -> dict:
    return {"order_id": order.order_id, "status": order.status, "status_phrase": order_status_phrase(order.status),
            "total": order.total, "created_at": order.created_at, "items": list(order.items or [])}