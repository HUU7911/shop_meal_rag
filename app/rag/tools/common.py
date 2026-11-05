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
