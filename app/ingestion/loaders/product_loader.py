"""Loader `product_loader`: duyệt sản phẩm qua app.integrations.product_client
(không tự gọi HTTP trực tiếp). Trả về danh sách bản ghi thô (dict).
"""
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.integrations.product_client import ProductClient, ProductInfo

log = logging.getLogger("app.ingestion.loaders.product")


class ProductLoader:
    def __init__(self, client: ProductClient | None = None):
        self.client = client or ProductClient()

    async def load_all(self, page_size: int = 100) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        try:
            items_iterator = self.client.iter_all(page_size=page_size)
            if hasattr(items_iterator, "__aiter__"):
                async for item in items_iterator:
                    records.append(self._to_dict(item))
            elif hasattr(items_iterator, "__iter__"):
                for item in items_iterator:
                    records.append(self._to_dict(item))
        except NotImplementedError:
            log.warning("ProductClient.iter_all chưa được implement bởi Member 01. Bỏ qua nạp sản phẩm.")
        except Exception as exc:
            log.error("Lỗi khi nạp sản phẩm từ ProductClient: %s", exc, exc_info=True)

        log.info("ProductLoader nạp được %d sản phẩm", len(records))
        return records

    @staticmethod
    def _to_dict(item: Any) -> dict[str, Any]:
        if isinstance(item, ProductInfo):
            return {
                "product_id": item.product_id,
                "name": item.name,
                "description": item.description,
                "category": item.category,
                "product_type": item.product_type,
                "price": item.price,
                "status": item.status,
                "url": item.url,
            }
        if isinstance(item, dict):
            return item
        return dict(item)
