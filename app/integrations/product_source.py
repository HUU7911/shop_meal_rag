"""Chọn nguồn dữ liệu sản phẩm theo PRODUCT_SOURCE: `file` (mặc định) hoặc `service` (Product Service)."""
from app.core.config import get_settings
from app.integrations.file_product_client import FileProductClient
from app.integrations.product_client import ProductClient


def create_product_client(settings=None):
    settings = settings or get_settings()
    if settings.product_source == "service":
        return ProductClient()
    return FileProductClient(settings.product_data_file)