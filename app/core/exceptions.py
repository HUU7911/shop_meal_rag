"""Handler chuẩn hóa lỗi API: mọi lỗi đều trả {"error": {code, message, requestId}}."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import (
    AppError,
    AuthenticationError,
    ConfigurationError,
    ConflictError,
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
    "ConflictError",
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
    "error_body",
    "register_exception_handlers",
]

log = logging.getLogger(__name__)

_HTTP_CODES = {
    400: "BAD_REQUEST",
    401: "AUTHENTICATION_ERROR",
    403: "PERMISSION_DENIED",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def error_body(code: str, message: str, request_id: str | None) -> dict:
    return {"error": {"code": code, "message": message, "requestId": request_id}}


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _with_request_id(headers: dict[str, str] | None, request_id: str | None) -> dict[str, str]:
    merged = dict(headers or {})
    if request_id:
        merged["X-Request-ID"] = request_id
    return merged


def _validation_message(exc: RequestValidationError) -> str:
    """Tóm tắt lỗi validate, KHÔNG lặp lại giá trị người dùng gửi (có thể chứa PII)."""
    parts = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(x) for x in err.get("loc", ()) if x not in ("body", "query", "path"))
        parts.append(f"{loc or 'request'}: {err.get('msg', 'không hợp lệ')}")
    return "Dữ liệu không hợp lệ: " + "; ".join(parts) if parts else "Dữ liệu không hợp lệ."


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        request_id = _request_id(request)
        if exc.status_code >= 500:
            log.error(
                "Application error: code=%s request_id=%s", exc.code, request_id, exc_info=exc
            )
        else:
            log.warning("Client error: code=%s request_id=%s", exc.code, request_id)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, request_id),
            headers=_with_request_id(exc.headers, request_id),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = _request_id(request)
        return JSONResponse(
            status_code=422,
            content=error_body("VALIDATION_ERROR", _validation_message(exc), request_id),
            headers=_with_request_id(None, request_id),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        request_id = _request_id(request)
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else code
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, message, request_id),
            headers=_with_request_id(getattr(exc, "headers", None), request_id),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = _request_id(request)
        log.error(
            "Unhandled exception: request_id=%s path=%s",
            request_id,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=500,
            content=error_body("INTERNAL_ERROR", "Đã xảy ra lỗi hệ thống.", request_id),
            headers=_with_request_id(None, request_id),
        )
