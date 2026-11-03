"""Client Order Service. LUÔN chuyển JWT của chính user; không tra đơn của người khác."""
from dataclasses import dataclass


@dataclass
class OrderInfo:
    order_id: str
    status: str
    total: float
    created_at: str
    items: list[dict]


class OrderClient:
    async def get_order(self, order_id: str, *, user_token: str) -> OrderInfo | None:
        raise NotImplementedError  # TODO

    async def list_recent(self, *, user_token: str, limit: int = 5) -> list[OrderInfo]:
        raise NotImplementedError
