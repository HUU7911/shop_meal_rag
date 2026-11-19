from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.core.dependencies import HealthServiceDep

router = APIRouter()


@router.get("/health")
async def liveness() -> dict:
    """Liveness: tiến trình còn sống (không kiểm tra phụ thuộc)."""
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness(service: HealthServiceDep) -> JSONResponse:
    """Readiness: ping MySQL, Redis, Qdrant; kiểm tra cấu hình LLM. 503 khi thiếu phụ thuộc bắt buộc."""
    report = await service.check_all()
    return JSONResponse(report, status_code=503 if report["status"] == "unavailable" else 200)
