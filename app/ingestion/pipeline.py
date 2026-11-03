"""Chạy ingestion: load -> clean -> plan (registry) -> chunk -> embed -> upsert -> ghi run log.
Idempotent: chạy lại nhiều lần không tạo dữ liệu trùng. Một tài liệu lỗi không làm hỏng cả job."""


async def run(mode: str = "incremental") -> dict:
    raise NotImplementedError  # TODO(Member 03) -> {"added": n, "updated": n, "deleted": n, "skipped": n}
