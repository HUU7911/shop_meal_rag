"""Đọc/ghi bảng ingestion_documents & ingestion_runs.

Incremental: so content_hash nguồn với registry -> ADD (mới) / UPDATE (hash đổi) / SKIP (giống) /
DELETE (có trong registry nhưng không còn ở nguồn, hoặc enabled=false)."""


class IngestionRegistry:
    async def plan(self, content_type: str, source_hashes: dict[str, str]) -> dict[str, list[str]]:
        raise NotImplementedError  # TODO(Member 03) -> {"add": [...], "update": [...], "delete": [...], "skip": [...]}
