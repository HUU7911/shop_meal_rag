
"""Hệ thống exception thuần Python để các module dùng chung."""


class AppError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500

    def __init__(
        self,
        message: str = "",
        *,
        details: dict | None = None,
        headers: dict[str, str] | None = None,
    ):
        super().__init__(message or self.code)
        self.message = message or self.code
        self.details = details if details is not None else {}
        self.headers = headers if headers is not None else {}  # vd. Retry-After cho 429


class ConfigurationError(AppError):
    code = "CONFIGURATION_ERROR"
    status_code = 500


class ValidationFailed(AppError):
    code = "VALIDATION_ERROR"
    status_code = 422


class AuthenticationError(AppError):
    code = "AUTHENTICATION_ERROR"
    status_code = 401


class PermissionDenied(AppError):
    code = "PERMISSION_DENIED"
    status_code = 403


class NotFoundError(AppError):
    code = "NOT_FOUND"
    status_code = 404


class ConflictError(AppError):
    code = "CONFLICT"
    status_code = 409


class ConversationError(AppError):
    code = "CONVERSATION_ERROR"
    status_code = 400


class RateLimited(AppError):
    code = "RATE_LIMITED"
    status_code = 429


class GuardrailBlocked(AppError):
    code = "GUARDRAIL_BLOCKED"
    status_code = 400


class EmbeddingError(AppError):
    code = "EMBEDDING_ERROR"
    status_code = 502


class RetrievalError(AppError):
    code = "RETRIEVAL_ERROR"
    status_code = 502


class VectorDatabaseError(AppError):
    code = "VECTOR_DB_ERROR"
    status_code = 503


class GenerationError(AppError):
    code = "GENERATION_ERROR"
    status_code = 502


class UpstreamUnavailableError(AppError):
    code = "UPSTREAM_UNAVAILABLE"
    status_code = 503
