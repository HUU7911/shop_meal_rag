"""Client Order Service. LUÔN chuyển JWT của chính user; không tra đơn của người khác.

GIẢ ĐỊNH VỀ API (chưa chốt - docs/CONTRACTS.md §5):
  GET {ORDER_SERVICE_URL}/api/v1/order/orders/{id}   (Order Service tự kiểm tra đơn thuộc user trong JWT)
  GET {ORDER_SERVICE_URL}/api/v1/order/orders/me?size=N   (đơn của chính user, mới nhất trước)
Không dùng service account. 403/404 -> None (không tiết lộ đơn của người khác có tồn tại hay không).
"""
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings
from app.integrations.http import ServiceHttpClient
from app.integrations.product_client import _first, _unwrap_page

ORDERS_PATH = "/api/v1/order/orders"
MY_ORDERS_PATH = "/api/v1/order/orders/me"
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass
class OrderInfo:
    order_id: str
    status: str
    total: float
    created_at: str
    items: list[dict]


def parse_order(raw: dict[str, Any]) -> OrderInfo | None:
    oid = _first(raw, "order_id", "orderId", "id")
    if oid is None:
        return None
    try:
        total = float(_first(raw, "total", "totalPrice", "totalAmount", "total_amount", default=0) or 0)
    except (TypeError, ValueError):
        total = 0.0
    raw_items = _first(raw, "items", "orderItems", "orderDetails", "details", default=[]) or []
    items = []
    for it in raw_items:
        if not isinstance(it, dict):
            continue
        items.append({
            "name": str(_first(it, "name", "productName", "product_name", default="?")),
            "quantity": _first(it, "quantity", "qty", default=1),
        })
    return OrderInfo(
        order_id=str(oid),
        status=str(_first(raw, "status", "orderStatus", default="UNKNOWN")).upper(),
        total=total,
        created_at=str(_first(raw, "created_at", "createdAt", "orderDate", "orderedAt", default="")),
        items=items,
    )


class OrderClient:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float | None = None,
        max_retries: int = 2,
        orders_path: str = ORDERS_PATH,
        my_orders_path: str = MY_ORDERS_PATH,
        transport: httpx.AsyncBaseTransport | None = None,
        http: ServiceHttpClient | None = None,
    ):
        settings = get_settings()
        self.orders_path = orders_path.rstrip("/")
        self.my_orders_path = my_orders_path
        self._http = http or ServiceHttpClient(
            base_url or settings.order_service_url,
            timeout=timeout if timeout is not None else settings.service_http_timeout_seconds,
            max_retries=max_retries,
            transport=transport,
            name="Order Service",
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_order(self, order_id: str, *, user_token: str) -> OrderInfo | None:
        if not user_token:
            raise ValueError("OrderClient cần JWT của chính người dùng")
        if not _SAFE_ID.match(str(order_id)):
            return None
        data = await self._http.get_json(
            f"{self.orders_path}/{quote(str(order_id), safe='')}", bearer_token=user_token
        )
        if isinstance(data, dict):
            for wrap in ("data", "result"):
                if isinstance(data.get(wrap), dict):
                    data = data[wrap]
                    break
        return parse_order(data) if isinstance(data, dict) else None

    async def list_recent(self, *, user_token: str, limit: int = 5) -> list[OrderInfo]:
        if not user_token:
            raise ValueError("OrderClient cần JWT của chính người dùng")
        data = await self._http.get_json(
            self.my_orders_path, params={"page": 0, "size": limit}, bearer_token=user_token
        )
        if data is None:
            return []
        raw_items, _ = _unwrap_page(data)
        orders = [o for o in (parse_order(r) for r in raw_items if isinstance(r, dict)) if o]
        return orders[:limit]
