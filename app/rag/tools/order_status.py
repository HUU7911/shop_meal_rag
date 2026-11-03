"""Tool tra đơn hàng của CHÍNH user qua OrderClient + JWT của user.
Guest -> trả fallback LOGIN_REQUIRED, không gọi service."""


async def order_status(order_id: str | None, *, user_token: str | None) -> dict:
    raise NotImplementedError  # TODO(Member 02)
