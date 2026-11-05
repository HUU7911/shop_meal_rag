"""Handler chuẩn hóa lỗi API. Các class lỗi nằm ở app/core/errors.py (re-export tại đây)."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import *  # noqa: F401,F403
from app.core.errors import AppError


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message,
                               "requestId": getattr(request.state, "request_id", None)}},
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Không lộ chi tiết nội bộ ra client; chi tiết nằm trong log (kèm request_id).
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "Đã xảy ra lỗi hệ thống.",
                               "requestId": getattr(request.state, "request_id", None)}},
        )
