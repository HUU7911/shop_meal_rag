"""Handler chuẩn hóa lỗi API."""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import (
    AppError,
    AuthenticationError,
    ConfigurationError,
    ConversationError,
    EmbeddingError,
    GenerationError,
    GuardrailBlocked,
    NotFoundError,
    PermissionDenied,
    RateLimited,
    RetrievalError,
    UpstreamUnavailableError,
    ValidationFailed,
    VectorDatabaseError,
)

__all__ = [
    "AppError",
    "AuthenticationError",
    "ConfigurationError",
    "ConversationError",
    "EmbeddingError",
    "GenerationError",
    "GuardrailBlocked",
    "NotFoundError",
    "PermissionDenied",
    "RateLimited",
    "RetrievalError",
    "UpstreamUnavailableError",
    "ValidationFailed",
    "VectorDatabaseError",
    "register_exception_handlers",
]

log = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)

        if exc.status_code >= 500:
            log.error(
                "Application error: code=%s request_id=%s",
                exc.code,
                request_id,
                exc_info=True,
            )
        else:
            log.warning(
                "Client error: code=%s request_id=%s",
                exc.code,
                request_id,
            )

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "requestId": request_id,
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)

        log.exception(
            "Unhandled exception: request_id=%s path=%s",
            request_id,
            request.url.path,
        )

        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Đã xảy ra lỗi hệ thống.",
                    "requestId": request_id,
                }
            },
        )
