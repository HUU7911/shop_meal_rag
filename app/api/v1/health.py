from fastapi import APIRouter

from app.services.health_service import HealthService

router = APIRouter()


@router.get("/health")
async def liveness() -> dict:
    """Liveness: tiến trình còn sống (không kiểm tra phụ thuộc)."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness() -> dict:
    """Readiness: kiểm tra Qdrant, Redis, MySQL, LLM."""
    return await HealthService().check_all()
