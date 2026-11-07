"""Loader `document_loader`: đọc các tài liệu bổ sung (markdown/txt) trong data/documents/
và trả về bản ghi thô (dict). Không chunk hay embed ở đây.
"""
import logging
from pathlib import Path

from app.ingestion.loaders.policy_loader import parse_front_matter

log = logging.getLogger("app.ingestion.loaders.document")


class DocumentLoader:
    def __init__(self, directory: Path | str | None = None):
        self.directory = Path(directory) if directory else Path("data/documents")

    def load(self) -> list[dict]:
        records: list[dict] = []
        if not self.directory.exists():
            log.warning("Thư mục Documents không tồn tại: %s", self.directory)
            return records

        for file_path in sorted(self.directory.glob("*.*")):
            if file_path.suffix.lower() not in {".md", ".txt"}:
                continue
            try:
                raw_text = file_path.read_text(encoding="utf-8")
                meta, body = parse_front_matter(raw_text)
                doc_id = str(meta.get("document_id") or file_path.stem)
                title = str(meta.get("title") or file_path.stem)

                record = {
                    "document_id": doc_id,
                    "title": title,
                    "version": str(meta.get("version", "1.0")),
                    "enabled": meta.get("enabled", True),
                    "category": str(meta.get("category", "DOCUMENT")).upper(),
                    "content": body,
                    "_source_file": str(file_path),
                }
                records.append(record)
            except Exception as exc:
                log.warning("Lỗi khi đọc file Document %s: %s", file_path, exc, exc_info=True)

        log.info("DocumentLoader nạp được %d bản ghi từ %s", len(records), self.directory)
        return records
