"""Kiểm tra sức khỏe các phụ thuộc cho /health/ready."""


class HealthService:
    async def check_all(self) -> dict:
        # TODO(Member 01): ping thật Qdrant, Redis, MySQL (timeout ngắn); LLM chỉ kiểm tra cấu hình.
        checks = {"qdrant": "unknown", "redis": "unknown", "mysql": "unknown", "llm": "unknown"}
        return {"status": "unknown", "checks": checks}
