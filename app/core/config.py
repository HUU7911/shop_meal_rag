"""Cấu hình ứng dụng. Tên biến khớp 1-1 với .env.example."""
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # App
    app_name: str = "shop-meal-rag"
    app_env: str = "development"
    app_port: int = 8000
    api_prefix: str = "/api/v1/chatbot"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # Auth
    jwt_public_key: str = ""
    jwt_jwks_url: str = ""
    jwt_algorithm: str = "RS256"
    jwt_audience: str = ""
    trust_gateway_user_header: bool = False
    allow_guest: bool = True
    internal_api_key: SecretStr = SecretStr("")

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_database: str = "shop_meal_chatbot"
    mysql_user: str = "rag_user"
    mysql_password: SecretStr = SecretStr("")

    # Redis
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: SecretStr = SecretStr("")

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: SecretStr = SecretStr("")
    qdrant_collection: str = "shop_meal_knowledge"

    # Embedding / rerank
    embedding_provider: str = "sentence-transformers"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_device: str = "cpu"
    rerank_enabled: bool = True
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_device: str = ""                   # "" = dùng EMBEDDING_DEVICE
    rerank_max_length: int = 512
    rerank_candidates: int = 0                # 0 = rerank toàn bộ top_k

    # RAG
    rag_enabled: bool = False                 # bật khi Qdrant/LLM/model đã sẵn sàng
    context_max_tokens: int = 1800
    support_contact: str = "bộ phận chăm sóc khách hàng của Shop Meal"

    # Retrieval
    retrieval_top_k: int = 8
    rerank_top_n: int = 4
    retrieval_score_threshold: float = 0.05
    hybrid_enabled: bool = True

    # LLM
    llm_enabled: bool = False
    llm_provider: str = ""
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = ""
    llm_timeout_seconds: int = 30
    llm_max_retries: int = 2
    llm_max_output_tokens: int = 800
    # Để trống nếu không gửi reasoning_effort.
    llm_reasoning_effort: str = ""
    # Tắt nếu LLM server không hỗ trợ stream_options.include_usage.
    llm_stream_usage: bool = True
    llm_fallback_provider: str = ""
    llm_fallback_model: str = ""

    # Conversation
    history_max_turns: int = 6
    history_max_tokens: int = 1500
    message_max_length: int = Field(1000, ge=1)
    rate_limit_per_minute: int = 20
    history_retention_days: int = 90

    # Shop Meal services
    product_service_url: str = "http://localhost:8081"
    order_service_url: str = "http://localhost:8082"
    service_http_timeout_seconds: float = 5.0
    kafka_bootstrap_servers: str = ""

    @property
    def mysql_url(self) -> str:
        pw = self.mysql_password.get_secret_value()
        return (
            f"mysql+asyncmy://{self.mysql_user}:{pw}@{self.mysql_host}:{self.mysql_port}"
            f"/{self.mysql_database}?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        pw = self.redis_password.get_secret_value()
        auth = f":{pw}@" if pw else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


_PLACEHOLDER_PREFIX = "change"


def validate_production_settings(settings: Settings) -> None:
    """Từ chối khởi động production với cấu hình bảo mật yếu (docs/SECURITY.md)."""
    from app.core.errors import ConfigurationError

    if settings.app_env.lower() != "production":
        return
    secrets = {
        "INTERNAL_API_KEY": settings.internal_api_key.get_secret_value(),
        "MYSQL_PASSWORD": settings.mysql_password.get_secret_value(),
        "REDIS_PASSWORD": settings.redis_password.get_secret_value(),
        "QDRANT_API_KEY": settings.qdrant_api_key.get_secret_value(),
    }
    weak = [k for k, v in secrets.items() if not v or v.lower().startswith(_PLACEHOLDER_PREFIX)]
    if weak:
        raise ConfigurationError(f"Production: cần đặt giá trị thật cho {', '.join(weak)}.")
    if not (settings.jwt_public_key or settings.jwt_jwks_url):
        raise ConfigurationError("Production: cần JWT_PUBLIC_KEY hoặc JWT_JWKS_URL.")
    if "*" in settings.cors_origin_list:
        raise ConfigurationError("Production: CORS_ORIGINS không được là '*'.")
    if not settings.rag_enabled:
        raise ConfigurationError("Production: RAG_ENABLED phải bật (không dùng MockRAGEngine).")


@lru_cache
def get_settings() -> Settings:
    return Settings()
