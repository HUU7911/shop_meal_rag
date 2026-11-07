"""Loader `faq_loader`: đọc các file FAQ JSON và trả về bản ghi thô (dict).
Không chunk hay embed ở đây.
"""
import json
import logging
from pathlib import Path

log = logging.getLogger("app.ingestion.loaders.faq")


class FAQLoader:
    def __init__(self, directory: Path | str | None = None):
        self.directory = Path(directory) if directory else Path("data/faq")

    def load(self) -> list[dict]:
        records: list[dict] = []
        if not self.directory.exists():
            log.warning("Thư mục FAQ không tồn tại: %s", self.directory)
            return records

        for file_path in sorted(self.directory.glob("*.json")):
            try:
                content = file_path.read_text(encoding="utf-8")
                items = json.loads(content)
                if not isinstance(items, list):
                    log.warning("File FAQ %s không phải danh sách JSON hợp lệ, bỏ qua", file_path)
                    continue

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item["_source_file"] = str(file_path)
                    records.append(item)
            except Exception as exc:
                log.warning("Lỗi khi đọc file FAQ %s: %s", file_path, exc, exc_info=True)

        log.info("FAQLoader nạp được %d bản ghi từ %s", len(records), self.directory)
        return records
