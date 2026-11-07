"""Loader `policy_loader`: đọc các file Markdown chính sách (có YAML front-matter)
và trả về bản ghi thô (dict). Không chunk hay embed ở đây.
"""
import logging
import re
from pathlib import Path

log = logging.getLogger("app.ingestion.loaders.policy")

_FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


def parse_front_matter(raw: str) -> tuple[dict, str]:
    match = _FRONT_MATTER_RE.match(raw)
    if not match:
        return {}, raw

    meta = {}
    for line in match.group(1).splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip().strip("'\"")
            if val.lower() == "true":
                val = True
            elif val.lower() == "false":
                val = False
            meta[key] = val
    return meta, match.group(2).strip()


class PolicyLoader:
    def __init__(self, directory: Path | str | None = None):
        self.directory = Path(directory) if directory else Path("data/policies")

    def load(self) -> list[dict]:
        records: list[dict] = []
        if not self.directory.exists():
            log.warning("Thư mục Policies không tồn tại: %s", self.directory)
            return records

        for file_path in sorted(self.directory.glob("*.md")):
            try:
                raw_text = file_path.read_text(encoding="utf-8")
                meta, body = parse_front_matter(raw_text)
                policy_id = str(meta.get("policy_id") or file_path.stem)
                title = str(meta.get("title") or file_path.stem)

                record = {
                    "policy_id": policy_id,
                    "title": title,
                    "version": str(meta.get("version", "1.0")),
                    "effective_date": str(meta.get("effective_date", "")),
                    "enabled": meta.get("enabled", True),
                    "content": body,
                    "_source_file": str(file_path),
                }
                records.append(record)
            except Exception as exc:
                log.warning("Lỗi khi đọc file Policy %s: %s", file_path, exc, exc_info=True)

        log.info("PolicyLoader nạp được %d bản ghi từ %s", len(records), self.directory)
        return records
