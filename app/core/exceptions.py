"""Exception dùng chung + handler chuẩn hóa lỗi API."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(self, message: str = "", *, details: dict | None = None):
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details = details or {}


class ConfigurationError(AppError):    code, status_code = "CONFIGURATION_ERROR", 500
class ValidationFailed(AppError):      code, status_code = "VALIDATION_ERROR", 422
class AuthenticationError(AppError):   code, status_code = "AUTHENTICATION_ERROR", 401
class PermissionDenied(AppError):      code, status_code = "PERMISSION_DENIED", 403
class NotFoundError(AppError):         code, status_code = "NOT_FOUND", 404
class ConversationError(AppError):     code, status_code = "CONVERSATION_ERROR", 400
class RateLimited(AppError):           code, status_code = "RATE_LIMITED", 429
class GuardrailBlocked(AppError):      code, status_code = "GUARDRAIL_BLOCKED", 400
class EmbeddingError(AppError):        code, status_code = "EMBEDDING_ERROR", 502
class RetrievalError(AppError):        code, status_code = "RETRIEVAL_ERROR", 502
class VectorDatabaseError(AppError):   code, status_code = "VECTOR_DB_ERROR", 503
class GenerationError(AppError):       code, status_code = "GENERATION_ERROR", 502
class UpstreamUnavailableError(AppError): code, status_code = "UPSTREAM_UNAVAILABLE", 503


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
