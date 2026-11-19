from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, status

from app.core.dependencies import CurrentUserDep, IngestionServiceDep
from app.core.errors import PermissionDenied
from app.core.security import is_valid_internal_key
from app.schemas.ingestion_schema import IngestionRunResponse

router = APIRouter()

InternalKey = Annotated[str | None, Header(alias="X-Internal-Key")]


async def require_admin(user: CurrentUserDep, x_internal_key: InternalKey = None) -> None:
    """Cho phép ADMIN (JWT) hoặc request có X-Internal-Key hợp lệ."""
    if not (user.is_admin or is_valid_internal_key(x_internal_key)):
        raise PermissionDenied("Chỉ dành cho quản trị.")


@router.post(
    "/ingestion/run",
    dependencies=[Depends(require_admin)],
    response_model=IngestionRunResponse,
    response_model_by_alias=True,
    status_code=status.HTTP_202_ACCEPTED,
)
async def run_ingestion(
    service: IngestionServiceDep,
    mode: Literal["full", "incremental"] = "incremental",
) -> IngestionRunResponse:
    """Kích hoạt ingestion chạy nền, trả ngay run_id (409 nếu đang có lượt khác chạy)."""
    return await service.start(mode)


@router.get(
    "/ingestion/runs/{run_id}",
    dependencies=[Depends(require_admin)],
    response_model=IngestionRunResponse,
    response_model_by_alias=True,
)
async def get_ingestion_run(run_id: int, service: IngestionServiceDep) -> IngestionRunResponse:
    """Xem trạng thái/thống kê một lượt ingestion."""
    return await service.get_run(run_id)
