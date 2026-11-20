"""Nguồn sản phẩm cố định từ file (mặc định data/products/food.json) – thay cho Product Service.

Cùng giao diện với `ProductClient` (get / search / iter_all / aclose) nên `rag.tools` và `ingestion`
dùng được mà không phải sửa. File được nạp lại tự động khi nội dung thay đổi (so sánh mtime), nên chỉnh
food.json xong KHÔNG cần khởi động lại API; riêng dữ liệu trong Qdrant thì cần `make ingest-full`/`ingest-inc`.

Định dạng chấp nhận: mảng JSON, {"products": [...]}, hoặc JSONL (mỗi dòng một sản phẩm; đuôi .jsonl).
Trường: product_id, name, description, category, product_type, price, status, url
(đúng như data/products/food.json). Sản phẩm HIDDEN/OUT_OF_STOCK vẫn được trả về kèm trạng thái, giống
hành vi mong đợi của `rag.tools` ("ẩn/hết hàng vẫn trả để nói đúng thực tế").
"""
import json
import logging
import math
import re
import unicodedata
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.errors import UpstreamUnavailableError
from app.integrations.product_client import ProductInfo, parse_product

log = logging.getLogger("app.integrations.file_products")

REPO_ROOT = Path(__file__).resolve().parents[2]
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_TOKEN = re.compile(r"\w+")


def fold(text: str) -> str:
    """Bỏ dấu tiếng Việt + chữ thường, để 'com' khớp 'Cơm', 'tra dao' khớp 'Trà đào'."""
    text = unicodedata.normalize("NFD", str(text or "").lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _read_records(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in raw.splitlines() if line.strip()]
    data = json.loads(raw)
    if isinstance(data, dict):
        data = data.get("products") or data.get("items") or data.get("content") or []
    return list(data)


class FileProductClient:
    def __init__(self, path: str | Path = "data/products/food.json"):
        p = Path(path)
        self._path = p if p.is_absolute() else REPO_ROOT / p
        self._mtime_ns: int | None = None
        self._items: list[ProductInfo] = []
        self._by_id: dict[str, ProductInfo] = {}
        self._folded: dict[str, tuple[str, str, str, str]] = {}    # id -> (name, type, category, description)

    # ---------------- nạp dữ liệu ----------------
    def _ensure_loaded(self) -> None:
        try:
            mtime = self._path.stat().st_mtime_ns
        except OSError as exc:
            raise UpstreamUnavailableError(f"Không đọc được file sản phẩm: {self._path}") from exc
        if mtime == self._mtime_ns:
            return
        try:
            records = _read_records(self._path)
        except (OSError, ValueError) as exc:        # JSONDecodeError là ValueError
            raise UpstreamUnavailableError(f"File sản phẩm không hợp lệ: {self._path} ({exc})") from exc

        by_id: dict[str, ProductInfo] = {}
        for rec in records:
            info = parse_product(rec) if isinstance(rec, dict) else None
            if info is None:
                log.warning("Bỏ qua bản ghi sản phẩm không có id trong %s", self._path.name)
                continue
            if info.product_id in by_id:
                log.warning("Trùng product_id %s trong %s, lấy bản ghi sau", info.product_id, self._path.name)
            by_id[info.product_id] = info
        self._by_id = by_id
        self._items = list(by_id.values())
        self._folded = {
            i.product_id: (fold(i.name), fold(i.product_type), fold(i.category), fold(i.description))
            for i in self._items
        }
        self._mtime_ns = mtime
        log.info("Đã nạp %d sản phẩm từ %s", len(self._items), self._path)

    def count(self) -> int:
        """Số sản phẩm hiện có (raise nếu file lỗi). Dùng kiểm tra lúc khởi động."""
        self._ensure_loaded()
        return len(self._items)

    # ---------------- giao diện giống ProductClient ----------------
    async def aclose(self) -> None:
        return None

    async def get(self, product_id: str) -> ProductInfo | None:
        if not _SAFE_ID.match(str(product_id)):
            return None
        self._ensure_loaded()
        return self._by_id.get(str(product_id))

    async def search(
        self,
        *,
        keyword: str | None = None,
        category: str | None = None,
        max_price: float | None = None,
        min_price: float | None = None,
        page: int = 1,
        size: int = 10,
    ) -> tuple[list[ProductInfo], int]:
        """Trả (items, total); `page` bắt đầu từ 1.

        category: khớp không dấu với `category` HOẶC `product_type` (chứa nhau).
        keyword: tách từ, chấm điểm theo tên (3) > loại/danh mục (2) > mô tả (1); cần khớp ít nhất
        một nửa số từ. Không có keyword thì giữ thứ tự trong file.
        """
        self._ensure_loaded()
        wanted = fold(category) if category else None
        tokens = [t for t in _TOKEN.findall(fold(keyword or "")) if len(t) >= 2]
        need = math.ceil(len(tokens) / 2) if tokens else 0

        scored: list[tuple[int, int, ProductInfo]] = []
        for index, info in enumerate(self._items):
            if max_price is not None and info.price > max_price:
                continue
            if min_price is not None and info.price < min_price:
                continue
            name, ptype, cat, desc = self._folded[info.product_id]
            if wanted and wanted not in cat and wanted not in ptype:
                continue
            score = 0
            if tokens:
                hit = 0
                for t in tokens:
                    weight = 3 if t in name else 2 if (t in ptype or t in cat) else 1 if t in desc else 0
                    if weight:
                        hit += 1
                        score += weight
                if hit < need:
                    continue
            scored.append((score, index, info))

        scored.sort(key=lambda x: (-x[0], x[1]))
        total = len(scored)
        size = max(size, 1)
        start = (max(page, 1) - 1) * size
        return [info for _, _, info in scored[start:start + size]], total

    async def iter_all(self, page_size: int = 100) -> AsyncIterator[ProductInfo]:
        self._ensure_loaded()
        for info in list(self._items):
            yield info