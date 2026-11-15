"""DỮ LIỆU GIẢ để thử chatbot khi Product/Order Service thật chưa có. KHÔNG dùng cho production.

Dùng bởi `scripts/seed_faq.py --with-demo-products` (đưa mô tả món vào Qdrant) và `scripts/chat_cli.py`
(giá/trạng thái/đơn hàng LIVE giả). Mô tả món cố ý KHÔNG chứa thông tin dị ứng để thử guardrail.
"""
from app.integrations.order_client import OrderInfo
from app.integrations.product_client import ProductInfo

DEMO_PRODUCTS = [
    ProductInfo("product-001", "Cơm gà xối mỡ", "Cơm gà giòn da, ăn kèm dưa leo và nước mắm gừng.",
                "RICE", "MAIN", 45000, "AVAILABLE", "/products/product-001"),
    ProductInfo("product-002", "Cơm sườn nướng", "Sườn nướng mật ong, trứng ốp la, đồ chua.",
                "RICE", "MAIN", 55000, "AVAILABLE", "/products/product-002"),
    ProductInfo("product-003", "Bún bò Huế", "Nước dùng đậm đà, bò bắp, giò heo, rau sống.",
                "NOODLE", "MAIN", 50000, "OUT_OF_STOCK", "/products/product-003"),
    ProductInfo("product-004", "Trà đào cam sả", "Trà đào thanh mát, vị cam và hương sả.",
                "DRINK", "DRINK", 30000, "AVAILABLE", "/products/product-004"),
]


class DemoProductClient:
    async def get(self, product_id):
        return next((p for p in DEMO_PRODUCTS if p.product_id == product_id), None)

    async def search(self, *, keyword=None, category=None, max_price=None, page=1, size=10):
        items = [p for p in DEMO_PRODUCTS
                 if (category is None or p.category == category) and (max_price is None or p.price <= max_price)]
        return items[:size], len(items)

    async def iter_all(self, page_size: int = 100):
        for p in DEMO_PRODUCTS:
            yield p


class DemoOrderClient:
    """Chỉ trả đơn #123 và chỉ khi có token (mô phỏng Order Service kiểm tra quyền sở hữu)."""
    _ORDER = OrderInfo("123", "DELIVERING", 100000, "2026-11-05 10:30",
                       [{"name": "Cơm gà xối mỡ", "quantity": 1}, {"name": "Cơm sườn nướng", "quantity": 1}])

    async def get_order(self, order_id, *, user_token):
        return self._ORDER if user_token and order_id == "123" else None

    async def list_recent(self, *, user_token, limit=5):
        return [self._ORDER] if user_token else []
