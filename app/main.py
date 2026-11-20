import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api.v1 import api_router
from app.core.config import get_settings, validate_production_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware
from app.db.session import create_engine_and_sessionmaker
from app.integrations.order_client import OrderClient
from app.integrations.product_source import create_product_client
from app.services.container import build_services
from app.services.mock_rag_engine import MockRAGEngine

log = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    validate_production_settings(settings)

    db_engine, db_sessionmaker = create_engine_and_sessionmaker()
    redis = Redis.from_url(settings.redis_url, decode_responses=True)   # kết nối lười
    product_client, order_client = create_product_client(settings), OrderClient()
    close_rag = None
    services = None
    if settings.product_source == "file":
        try:
            log.info("Nguồn sản phẩm: file %s (%d sản phẩm)", settings.product_data_file, product_client.count())
        except Exception:  # noqa: BLE001
            log.warning("Không đọc được file sản phẩm %s", settings.product_data_file, exc_info=True)
    try:
        if settings.rag_enabled:
            from app.rag.factory import build_rag_engine

            rag_engine, close_rag = await build_rag_engine(settings, product_client, order_client)
        else:
            log.warning("RAG_ENABLED=false: dùng MockRAGEngine (câu trả lời GIẢ, chỉ để phát triển/test)")
            rag_engine = MockRAGEngine(settings.support_contact)

        services = build_services(
            settings, db_engine=db_engine, session_factory=db_sessionmaker,
            redis=redis, rag_engine=rag_engine,
        )
        try:
            recovered = await services.ingestion.recover()
            if recovered:
                log.warning("Đã đánh dấu FAILED %d lượt ingestion bị bỏ dở", recovered)
        except Exception:  # noqa: BLE001 - DB chưa migrate/chưa sẵn sàng: /health/ready sẽ báo
            log.warning("Không kiểm tra được lượt ingestion bỏ dở (DB chưa sẵn sàng?)", exc_info=True)

        app.state.db_engine = db_engine
        app.state.db_sessionmaker = db_sessionmaker
        app.state.redis = redis
        app.state.rag_engine = rag_engine
        app.state.services = services
        yield
    finally:
        if services is not None:
            await services.ingestion.aclose()
        if close_rag:
            await close_rag()
        await product_client.aclose()
        await order_client.aclose()
        await redis.aclose()
        await db_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    is_prod = settings.app_env.lower() == "production"
    app = FastAPI(
        title="Shop Meal RAG Chatbot",
        version="0.1.0",
        lifespan=lifespan,
        # Production: không công khai tài liệu API
        openapi_url=None if is_prod else f"{settings.api_prefix}/openapi.json",
        docs_url=None if is_prod else f"{settings.api_prefix}/docs",
        redoc_url=None,
    )
    origins = settings.cors_origin_list
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID", "X-Internal-Key"],
        expose_headers=["X-Request-ID", "Retry-After"],
        allow_credentials="*" not in origins,       # '*' kèm credentials là cấu hình không an toàn
    )
    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
