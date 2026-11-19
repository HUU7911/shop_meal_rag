import httpx
import pytest

from app.core.errors import AuthenticationError, UpstreamUnavailableError
from app.integrations.http import ServiceHttpClient
from app.integrations.order_client import OrderClient
from app.integrations.product_client import ProductClient


class Recorder:
    """Handler giả: trả lần lượt các phản hồi/ngoại lệ đã định, ghi lại mọi request."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []

    def __call__(self, request):
        self.requests.append(request)
        item = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(item, Exception):
            raise item
        return item


def make_http(handler, name="Product Service", retries=2):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    http = ServiceHttpClient("http://svc", timeout=1.0, max_retries=retries,
                             transport=httpx.MockTransport(handler), sleep=fake_sleep, name=name)
    http.sleeps = sleeps
    return http


PRODUCT = {"productId": "SM-0321", "name": "Trà đào", "description": "Thơm", "category": {"name": "Đồ uống"},
           "productType": "Trà", "price": 41000, "status": "available"}


async def test_product_get_maps_camel_case_and_builds_default_url():
    handler = Recorder(httpx.Response(200, json=PRODUCT))
    client = ProductClient(http=make_http(handler))
    info = await client.get("SM-0321")
    assert info.product_id == "SM-0321" and info.category == "Đồ uống" and info.price == 41000.0
    assert info.status == "AVAILABLE" and info.url == "/products/SM-0321"
    assert handler.requests[0].url.path.endswith("/products/SM-0321")


async def test_product_get_unknown_returns_none_and_unsafe_id_is_never_sent():
    handler = Recorder(httpx.Response(404))
    client = ProductClient(http=make_http(handler))
    assert await client.get("NOPE") is None
    assert await client.get("../../admin") is None            # chặn path traversal
    assert len(handler.requests) == 1                          # id lạ không tạo request nào


async def test_retries_transient_errors_with_backoff_then_succeeds():
    handler = Recorder(httpx.Response(503), httpx.ConnectError("x"), httpx.Response(200, json=PRODUCT))
    http = make_http(handler)
    info = await ProductClient(http=http).get("SM-0321")
    assert info is not None and len(handler.requests) == 3
    assert http.sleeps == [0.2, 0.4]


async def test_gives_up_after_retries_with_upstream_error():
    handler = Recorder(httpx.TimeoutException("slow"))
    http = make_http(handler, retries=2)
    with pytest.raises(UpstreamUnavailableError):
        await ProductClient(http=http).get("SM-0321")
    assert len(handler.requests) == 3


async def test_client_error_is_not_retried():
    handler = Recorder(httpx.Response(400))
    with pytest.raises(UpstreamUnavailableError):
        await ProductClient(http=make_http(handler)).get("SM-0321")
    assert len(handler.requests) == 1


async def test_search_uses_zero_based_page_and_spring_page_shape():
    body = {"content": [PRODUCT], "totalElements": 7}
    handler = Recorder(httpx.Response(200, json=body))
    items, total = await ProductClient(http=make_http(handler)).search(category="Đồ uống", max_price=50000, page=1, size=5)
    params = handler.requests[0].url.params
    assert params["page"] == "0" and params["size"] == "5" and params["maxPrice"] == "50000"
    assert "keyword" not in params                              # tham số None không được gửi
    assert total == 7 and [p.product_id for p in items] == ["SM-0321"]


async def test_iter_all_walks_every_page():
    def page(n, count):
        return {"content": [{**PRODUCT, "productId": f"P{n}-{i}"} for i in range(count)], "totalElements": 5}

    handler = Recorder(httpx.Response(200, json=page(0, 2)), httpx.Response(200, json=page(1, 2)),
                       httpx.Response(200, json=page(2, 1)))
    ids = [p.product_id async for p in ProductClient(http=make_http(handler)).iter_all(page_size=2)]
    assert ids == ["P0-0", "P0-1", "P1-0", "P1-1", "P2-0"] and len(handler.requests) == 3


ORDER = {"id": 123, "status": "delivering", "totalPrice": 90000, "createdAt": "2026-11-05T10:00:00",
         "orderItems": [{"productName": "Cơm gà", "quantity": 2}]}


async def test_order_forwards_only_the_users_own_token():
    handler = Recorder(httpx.Response(200, json=ORDER))
    client = OrderClient(http=make_http(handler, "Order Service"))
    order = await client.get_order("123", user_token="user-jwt")
    assert handler.requests[0].headers["authorization"] == "Bearer user-jwt"
    assert order.order_id == "123" and order.status == "DELIVERING" and order.total == 90000.0
    assert order.items == [{"name": "Cơm gà", "quantity": 2}]


async def test_order_of_someone_else_looks_like_not_found():
    client = OrderClient(http=make_http(Recorder(httpx.Response(403)), "Order Service"))
    assert await client.get_order("999", user_token="user-jwt") is None


async def test_order_expired_token_raises_authentication_error():
    client = OrderClient(http=make_http(Recorder(httpx.Response(401)), "Order Service"))
    with pytest.raises(AuthenticationError):
        await client.get_order("123", user_token="expired")


async def test_order_client_refuses_to_run_without_user_token():
    client = OrderClient(http=make_http(Recorder(httpx.Response(200, json=ORDER)), "Order Service"))
    with pytest.raises(ValueError):
        await client.get_order("123", user_token="")
    with pytest.raises(ValueError):
        await client.list_recent(user_token="")


async def test_list_recent_limits_results():
    body = {"content": [{**ORDER, "id": i} for i in range(1, 6)]}
    client = OrderClient(http=make_http(Recorder(httpx.Response(200, json=body)), "Order Service"))
    assert [o.order_id for o in await client.list_recent(user_token="t", limit=3)] == ["1", "2", "3"]
